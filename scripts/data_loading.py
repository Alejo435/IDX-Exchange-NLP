import os

import mysql.connector
import pandas as pd


"""
Choices:

- PROJECT_ROOT is built from the script's own location so outputs always in data/processed/ 
- Closing the connection in finally prevents leaked connections if the query throws.
"""
# resolve paths from the project root so the script works from any directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "data", "processed", "listing_sample.csv")

# minimum row count required by the week 1 specification
MIN_SAMPLE_ROWS = 500

# =============================================================================
# Configuration
# =============================================================================

# connection settings default to the values defined in docker-compose.yml
# env variables allow overrides without modifying source code.
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "root"),
    "database": os.getenv("DB_NAME", "real_estate"),
}


SAMPLE_SIZE = 1000
MIN_REMARK_LENGTH = 50

# fixed seed for reference in case another teammate uses it
RANDOM_SEED = 42

# =============================================================================
# Database Connection
# =============================================================================

def get_connection(config=None):
    return mysql.connector.connect(**(config or DB_CONFIG))

# =============================================================================
# Sample Extraction
# =============================================================================

# CHAR_LENGTH is used instead of LENGTH because LENGTH counts bytes
# Remarks containing multi-byte characters would otherwise pass the SQL
# filter while failing the character-based length check in the tests
SAMPLE_QUERY = """
    SELECT
        L_ListingID,
        L_Address,
        L_City,
        L_Keyword2     AS beds,
        LM_Dec_3       AS baths,
        L_SystemPrice  AS price,
        L_Remarks      AS remarks
    FROM rets_property
    WHERE L_Remarks IS NOT NULL
      AND CHAR_LENGTH(L_Remarks) > %s
    ORDER BY RAND(%s)
    LIMIT %s
"""

# Retrieve a random sample of listings with non-trivial remarks.
def load_listing_sample(conn, sample_size=SAMPLE_SIZE,
                        min_length=MIN_REMARK_LENGTH, seed=RANDOM_SEED):

    cursor = conn.cursor()
    try:
        # Parameters are passed separately from the SQL string so the
        # connector handles escaping.
        cursor.execute(SAMPLE_QUERY, (min_length, seed, sample_size))
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
    finally:
        cursor.close()

    return pd.DataFrame(rows, columns=columns)

# =============================================================================
# Output
# =============================================================================

# write the sample DataFrame to CSV, creating the output directory if needed
def save_sample(df, path=OUTPUT_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path, index=False)
    return path

# =============================================================================
# Entry Point
# =============================================================================

# extract the listing sample from MySQL and save it to CSV
def main():
    conn = get_connection()
    try:
        df = load_listing_sample(conn)
    finally:
        # close the connection even if the query fails
        conn.close()

    if len(df) < MIN_SAMPLE_ROWS:
        print(f"warning: only {len(df)} rows returned, week 1 requires at least {MIN_SAMPLE_ROWS}")

    path = save_sample(df)
    print(f"saved {len(df)} listings to {path}")


if __name__ == "__main__":
    main()