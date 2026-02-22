"""
Create the vendors table (if it doesn't exist) and load vendorData.csv into it.
Safe to re-run — uses ON CONFLICT DO UPDATE so existing rows are refreshed.
"""
import csv
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
CSV_PATH = Path(__file__).parent / "samples" / "vendorData.csv"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS vendors (
    vendor_id              VARCHAR(20)   PRIMARY KEY,
    vendor_name            VARCHAR(100)  NOT NULL,
    category               VARCHAR(50)   NOT NULL,
    product_or_service     VARCHAR(150)  NOT NULL,
    carbon_intensity       NUMERIC(10,4) NOT NULL CHECK (carbon_intensity >= 0),
    sustainability_score   SMALLINT      NOT NULL CHECK (sustainability_score BETWEEN 0 AND 100),
    distance_km_from_sme   NUMERIC(10,2) CHECK (distance_km_from_sme >= 0),
    created_at             TIMESTAMPTZ   DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vendors_category
    ON vendors(category);

CREATE INDEX IF NOT EXISTS idx_vendors_sustainability_score
    ON vendors(sustainability_score DESC);
"""

UPSERT_SQL = """
INSERT INTO vendors
    (vendor_id, vendor_name, category, product_or_service,
     carbon_intensity, sustainability_score, distance_km_from_sme)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (vendor_id) DO UPDATE SET
    vendor_name           = EXCLUDED.vendor_name,
    category              = EXCLUDED.category,
    product_or_service    = EXCLUDED.product_or_service,
    carbon_intensity      = EXCLUDED.carbon_intensity,
    sustainability_score  = EXCLUDED.sustainability_score,
    distance_km_from_sme  = EXCLUDED.distance_km_from_sme;
"""


def main() -> None:
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            # 1. Create the table and indexes
            cur.execute(CREATE_TABLE_SQL)
            print("vendors table ready.")

            # 2. Load CSV and upsert each row
            with CSV_PATH.open(newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                rows = list(reader)

            count = 0
            for row in rows:
                cur.execute(
                    UPSERT_SQL,
                    (
                        row["vendor_id"].strip(),
                        row["vendor_name"].strip(),
                        row["category"].strip(),
                        row["product_or_service"].strip(),
                        float(row["carbon_intensity"]),
                        int(row["sustainability_score"]),
                        float(row["distance_km_from_sme"]),
                    ),
                )
                count += 1

        conn.commit()
        print(f"Seeded {count} vendor rows successfully.")

        # 3. Quick verification print
        with conn.cursor() as cur:
            cur.execute(
                "SELECT vendor_id, vendor_name, category, sustainability_score "
                "FROM vendors ORDER BY sustainability_score DESC"
            )
            print(f"\n{'ID':<8} {'Name':<30} {'Category':<20} {'Score':>5}")
            print("-" * 68)
            for r in cur.fetchall():
                print(f"{r[0]:<8} {r[1]:<30} {r[2]:<20} {r[3]:>5}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
