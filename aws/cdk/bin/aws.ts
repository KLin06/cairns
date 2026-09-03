#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import { InferenceStack } from "../lib/inference-stack";

const app = new cdk.App();

// Required context/config - pass at synth/deploy time, e.g.:
//   cdk deploy \
//     -c modelBucketName=cairns-models \
//     -c alertEmail=you@example.com
//
// No database context is needed - this stack provisions its own RDS
// Postgres instance (see lib/inference-stack.ts) rather than assuming an
// externally-reachable database already exists.
const modelBucketName = app.node.tryGetContext("modelBucketName");
const alertEmail = app.node.tryGetContext("alertEmail");

if (!modelBucketName || !alertEmail) {
  throw new Error(
    "Missing required context. Pass -c modelBucketName=... -c alertEmail=... " +
      "(see aws/README.md for what each one is and how to set them up)."
  );
}

new InferenceStack(app, "CairnsAsyncInferenceStack", {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION,
  },
  modelBucketName,
  alertEmail,
});
