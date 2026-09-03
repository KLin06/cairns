import * as path from "path";
import * as cdk from "aws-cdk-lib";
import * as cloudwatch from "aws-cdk-lib/aws-cloudwatch";
import * as cloudwatch_actions from "aws-cdk-lib/aws-cloudwatch-actions";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as eventsources from "aws-cdk-lib/aws-lambda-event-sources";
import * as rds from "aws-cdk-lib/aws-rds";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as sns from "aws-cdk-lib/aws-sns";
import * as sns_subscriptions from "aws-cdk-lib/aws-sns-subscriptions";
import * as sqs from "aws-cdk-lib/aws-sqs";
import { Construct } from "constructs";

export interface InferenceStackProps extends cdk.StackProps {
  /**
   * Name of the existing S3 bucket holding condition_models.joblib (see
   * specs/007-docker-containerization). This stack does not create or own
   * the bucket, only reads from it. Trail descriptions no longer need a
   * copy here (unlike an earlier version of this stack) - conditions.py
   * reads them from the RDS instance below instead, per
   * server/db/migrations/0004_add_model_terrain_features.sql.
   */
  readonly modelBucketName: string;
  /** Defaults to "condition_models.joblib", matching spec 007's contract. */
  readonly modelS3Key?: string;
  /** Where DLQ-depth / worker-error alarms are emailed. */
  readonly alertEmail: string;
}

export class InferenceStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: InferenceStackProps) {
    super(scope, id, props);

    const modelBucket = s3.Bucket.fromBucketName(this, "ModelBucket", props.modelBucketName);

    // --- Networking: the Lambda runs in AWS and has no path to spec 007's
    // local docker-compose Postgres (FR-015), so this stack provisions its
    // own database instead of assuming one is already reachable. Three
    // subnet tiers: public (NAT lives here), private-with-egress (the
    // Lambda - needs outbound internet for Open-Meteo, per SYSTEM_DESIGN.md
    // 6.5), and isolated (the database - no route to the internet at all,
    // reachable only from inside this VPC). ---
    const vpc = new ec2.Vpc(this, "InferenceVpc", {
      maxAzs: 2,
      natGateways: 1, // one, not one-per-AZ, to keep cost down (FR-016 needs private networking, not HA NAT)
      subnetConfiguration: [
        { name: "public", subnetType: ec2.SubnetType.PUBLIC, cidrMask: 24 },
        { name: "lambda-private", subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS, cidrMask: 24 },
        { name: "database-isolated", subnetType: ec2.SubnetType.PRIVATE_ISOLATED, cidrMask: 24 },
      ],
    });

    // S3 and DynamoDB traffic from the Lambda's private subnet routes
    // through these free gateway endpoints instead of the NAT Gateway -
    // cheaper and lower-latency for the two AWS services this Lambda talks
    // to most. Open-Meteo (arbitrary internet host) still needs the NAT
    // Gateway; there's no endpoint type for "the general internet."
    vpc.addGatewayEndpoint("S3Endpoint", { service: ec2.GatewayVpcEndpointAwsService.S3 });
    vpc.addGatewayEndpoint("DynamoDbEndpoint", { service: ec2.GatewayVpcEndpointAwsService.DYNAMODB });

    // --- Database: a plain single-instance RDS Postgres, not Aurora
    // Serverless v2. Aurora was the original choice here specifically for
    // its pay-for-what-you-use scaling (see SYSTEM_DESIGN.md /
    // DESIGN_JUSTIFICATION.md), but this AWS account's plan rejects Aurora
    // cluster creation outright ("free plan accounts" require an
    // undocumented "WithExpressConfiguration" flag that isn't exposed
    // anywhere in aws-cdk-lib - an account-level restriction, not something
    // fixable in this stack's code). A db.t3.micro instance is both
    // RDS-Free-Tier-eligible (Aurora isn't) and, at this workload's tiny
    // scale, cheaper in raw dollars than Aurora Serverless v2's ACU pricing
    // floor - see SYSTEM_DESIGN.md's updated 6.5 for the full tradeoff.
    const database = new rds.DatabaseInstance(this, "TrailsDatabase", {
      engine: rds.DatabaseInstanceEngine.postgres({ version: rds.PostgresEngineVersion.VER_16_13 }),
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MICRO),
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      databaseName: "cairns",
      allocatedStorage: 20,
      // Auto-generates a Secrets Manager secret ({username, password}) -
      // handler.py combines it with the plain (non-secret) host/port/dbname
      // env vars below to build DATABASE_URL. Excludes characters that would
      // need extra escaping inside a postgresql:// URL.
      credentials: rds.Credentials.fromGeneratedSecret("cairns_app", {
        excludeCharacters: " %+~`#$&*()|[]{}:;<>?!'/@\"\\",
      }),
      multiAz: false,
      publiclyAccessible: false,
      storageEncrypted: true,
      // POC-friendly defaults so `cdk destroy` actually tears this down
      // during iteration - flip to SNAPSHOT/RETAIN + deletionProtection:
      // true once this holds real production data (see aws/README.md).
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      deletionProtection: false,
    });

    // --- Dead-letter queue: requests that fail maxReceiveCount times land
    // here instead of being retried forever or silently dropped (FR-007). ---
    const deadLetterQueue = new sqs.Queue(this, "PredictionDeadLetterQueue", {
      queueName: "cairns-prediction-requests-dlq",
      retentionPeriod: cdk.Duration.days(14),
      encryption: sqs.QueueEncryption.SQS_MANAGED,
    });

    // --- Main request queue (standard, not FIFO - see SYSTEM_DESIGN.md 6.1
    // for why ordering/exactly-once don't matter for this workload). ---
    const requestQueue = new sqs.Queue(this, "PredictionRequestQueue", {
      queueName: "cairns-prediction-requests",
      // Must exceed the Lambda's own timeout (90s below) with margin, so a
      // message isn't returned to the queue while still being processed.
      visibilityTimeout: cdk.Duration.seconds(180),
      retentionPeriod: cdk.Duration.days(4),
      encryption: sqs.QueueEncryption.SQS_MANAGED,
      deadLetterQueue: {
        queue: deadLetterQueue,
        maxReceiveCount: 5,
      },
    });

    // --- Durable, keyed storage for computed predictions (FR-005/FR-006).
    // On-demand billing: this workload is bursty/nightly-batch-shaped, not
    // continuous - see SYSTEM_DESIGN.md 6.3 for why provisioned+autoscaling
    // isn't a better fit here. ---
    const predictionsTable = new dynamodb.Table(this, "PredictionsTable", {
      tableName: "cairns-trail-conditions-predictions",
      partitionKey: { name: "trailId", type: dynamodb.AttributeType.STRING },
      sortKey: { name: "date", type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    // --- Compute: container image, not zip/layers - scikit-learn + pandas +
    // joblib are well past the 250MB zip limit. Reuses server/app + server/db
    // unmodified (see aws/lambda/Dockerfile), per constitution Principle II /
    // spec 008 FR-003: this is a second trigger, not a second
    // implementation. ---
    const predictionWorker = new lambda.DockerImageFunction(this, "PredictionWorker", {
      functionName: "cairns-prediction-worker",
      code: lambda.DockerImageCode.fromImageAsset(path.join(__dirname, "..", "..", ".."), {
        file: "aws/lambda/Dockerfile",
      }),
      memorySize: 1024,
      timeout: cdk.Duration.seconds(90),
      // No reservedConcurrentExecutions: this account's total Lambda
      // concurrency ceiling is low enough that reserving 50 violated AWS's
      // "at least 10 unreserved for the rest of the account" rule -
      // real-deploy discovery, same restricted-account theme as the Aurora
      // rejection above. The blast-radius cap this was meant to provide
      // (SYSTEM_DESIGN.md 6.2/9) is a nice-to-have, not a correctness
      // requirement - dropped rather than guessed at a number that might
      // still be too high for this account.
      // Must run where it can reach the isolated-subnet database (FR-015) -
      // the private-with-egress tier also gives it a path to Open-Meteo via
      // the NAT Gateway, and to S3/DynamoDB via the gateway endpoints above.
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      environment: {
        MODEL_S3_BUCKET: props.modelBucketName,
        MODEL_S3_KEY: props.modelS3Key ?? "condition_models.joblib",
        PREDICTIONS_TABLE_NAME: predictionsTable.tableName,
        DB_CREDENTIALS_SECRET_ARN: database.secret!.secretArn,
        DB_HOST: database.instanceEndpoint.hostname,
        DB_PORT: cdk.Token.asString(database.instanceEndpoint.port),
        DB_NAME: "cairns",
      },
    });

    // Least-privilege grants (FR-014) - no wildcard resource ARNs.
    modelBucket.grantRead(predictionWorker);
    predictionsTable.grantWriteData(predictionWorker);
    database.secret!.grantRead(predictionWorker);
    // Security-group-level access (FR-016): only this Lambda's security
    // group may reach Postgres's port, on top of the credential itself.
    database.connections.allowDefaultPortFrom(predictionWorker, "Prediction worker Lambda to Postgres");

    predictionWorker.addEventSource(
      new eventsources.SqsEventSource(requestQueue, {
        batchSize: 5,
        // A bad message in a batch of 5 shouldn't force the other 4 (which
        // may have already succeeded) to be reprocessed - see
        // SYSTEM_DESIGN.md 6.2.
        reportBatchItemFailures: true,
      })
    );

    // --- Alerting (FR-009/SC-007): fire the moment anything reaches the
    // DLQ, or the worker starts erroring systemically, rather than relying
    // on an operator to notice. ---
    const alertTopic = new sns.Topic(this, "PredictionAlerts", {
      topicName: "cairns-prediction-alerts",
    });
    alertTopic.addSubscription(new sns_subscriptions.EmailSubscription(props.alertEmail));

    const dlqDepthAlarm = new cloudwatch.Alarm(this, "DeadLetterQueueDepthAlarm", {
      alarmName: "cairns-prediction-dlq-depth",
      alarmDescription:
        "One or more prediction requests landed in the dead-letter queue after exhausting retries - see specs/008-aws-async-inference/spec.md FR-007/FR-009.",
      metric: deadLetterQueue.metricApproximateNumberOfMessagesVisible({
        period: cdk.Duration.minutes(5),
        statistic: "max",
      }),
      threshold: 1,
      evaluationPeriods: 1,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });
    dlqDepthAlarm.addAlarmAction(new cloudwatch_actions.SnsAction(alertTopic));

    const workerErrorsAlarm = new cloudwatch.Alarm(this, "WorkerErrorsAlarm", {
      alarmName: "cairns-prediction-worker-errors",
      alarmDescription: "The prediction worker Lambda is erroring on a significant share of invocations.",
      metric: predictionWorker.metricErrors({
        period: cdk.Duration.minutes(5),
        statistic: "sum",
      }),
      threshold: 5,
      evaluationPeriods: 1,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });
    workerErrorsAlarm.addAlarmAction(new cloudwatch_actions.SnsAction(alertTopic));

    new cdk.CfnOutput(this, "RequestQueueUrl", { value: requestQueue.queueUrl });
    new cdk.CfnOutput(this, "DeadLetterQueueUrl", { value: deadLetterQueue.queueUrl });
    new cdk.CfnOutput(this, "PredictionsTableName", { value: predictionsTable.tableName });
    new cdk.CfnOutput(this, "AlertTopicArn", { value: alertTopic.topicArn });
    new cdk.CfnOutput(this, "DatabaseEndpoint", { value: database.instanceEndpoint.hostname });
    new cdk.CfnOutput(this, "DatabaseCredentialsSecretArn", {
      value: database.secret!.secretArn,
      description: "Fetch with `aws secretsmanager get-secret-value` to run server/db/backfill.py against this database - see aws/README.md.",
    });
  }
}
