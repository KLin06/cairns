# Built with repo root as the Docker build context (see
# aws/cdk/lib/inference-stack.ts's fromImageAsset call) so this can COPY
# server/app and server/db directly - this worker reuses the existing
# prediction code unmodified rather than maintaining a second copy
# (constitution Principle II, specs/008-aws-async-inference/spec.md FR-003).
FROM public.ecr.aws/lambda/python:3.12

# 3.12 (Amazon Linux 2023) instead of 3.11 (Amazon Linux 2) deliberately -
# AL2's ancient default gcc (7.3.1) can't build numpy from source (needs
# gcc>=9.3), and AL2's old glibc has no matching prebuilt numpy wheel either.
# AL2023's modern toolchain avoids the problem instead of working around it
# with a manually-installed devtoolset.
RUN dnf install -y gcc gcc-c++ python3-devel && dnf clean all

COPY server/requirements.txt ${LAMBDA_TASK_ROOT}/requirements.txt
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY server/app ${LAMBDA_TASK_ROOT}/app
COPY server/db ${LAMBDA_TASK_ROOT}/db
COPY aws/lambda/handler.py ${LAMBDA_TASK_ROOT}/handler.py

CMD ["handler.lambda_handler"]
