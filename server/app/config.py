import os

# server/ and data/ are sibling directories at the repo root - the server
# reads whatever the data pipeline (data/scripts/...) has already produced
# on disk under data/datasets/, it doesn't run any of the scrape/clean/enrich
# stages itself and doesn't import any data/scripts Python code either -
# server/ is meant to run standalone with its own requirements.txt.
SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(SERVER_DIR)
DATASETS_DIR = os.path.join(REPO_ROOT, "data", "datasets")

CLEANED_REVIEWS_DIR = os.path.join(DATASETS_DIR, "cleaned_reviews")
ENRICHED_DESCRIPTIONS_DIR = os.path.join(DATASETS_DIR, "enriched_descriptions")
ROUTE_GEOMETRY_DIR = os.path.join(DATASETS_DIR, "route_geometry")

# condition_models.joblib now lives in S3 (see specs/007-docker-containerization)
# instead of data/datasets/models/ - fetched by conditions.py via boto3 and
# cached in memory for the process lifetime, not read off local disk.
MODEL_S3_BUCKET = os.environ.get("MODEL_S3_BUCKET")
MODEL_S3_KEY = os.environ.get("MODEL_S3_KEY")
