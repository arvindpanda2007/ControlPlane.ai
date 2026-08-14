import os

import psycopg


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://controlplane:controlplane@localhost:5433/controlplane",
)


def get_connection():
    return psycopg.connect(DATABASE_URL)