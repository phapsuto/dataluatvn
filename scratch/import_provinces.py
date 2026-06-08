import sqlite3
import os
import sys

def main():
    db_path = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/vietnamese_legal_documents.db"
    sql_path = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/scratch/vietnamese-provinces-database/postgresql/postgres_ImportData_vn_units.sql"
    
    if not os.path.exists(db_path):
        print(f"Error: Database {db_path} not found.")
        sys.exit(1)
        
    if not os.path.exists(sql_path):
        print(f"Error: SQL data file {sql_path} not found.")
        sys.exit(1)
        
    print("Connecting to database...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 1. Drop existing tables if they exist
    print("Cleaning up old administrative tables...")
    cursor.execute("DROP TABLE IF EXISTS wards;")
    cursor.execute("DROP TABLE IF EXISTS provinces;")
    cursor.execute("DROP TABLE IF EXISTS administrative_units;")
    cursor.execute("DROP TABLE IF EXISTS administrative_regions;")
    
    # 2. Create tables
    print("Creating administrative tables...")
    cursor.execute("""
    CREATE TABLE administrative_regions (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        name_en TEXT NOT NULL,
        code_name TEXT,
        code_name_en TEXT
    );
    """)
    
    cursor.execute("""
    CREATE TABLE administrative_units (
        id INTEGER PRIMARY KEY,
        full_name TEXT,
        full_name_en TEXT,
        short_name TEXT,
        short_name_en TEXT,
        code_name TEXT,
        code_name_en TEXT
    );
    """)
    
    cursor.execute("""
    CREATE TABLE provinces (
        code TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        name_en TEXT,
        full_name TEXT NOT NULL,
        full_name_en TEXT,
        code_name TEXT,
        administrative_unit_id INTEGER,
        FOREIGN KEY(administrative_unit_id) REFERENCES administrative_units(id)
    );
    """)
    
    cursor.execute("""
    CREATE TABLE wards (
        code TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        name_en TEXT,
        full_name TEXT,
        full_name_en TEXT,
        code_name TEXT,
        province_code TEXT,
        administrative_unit_id INTEGER,
        FOREIGN KEY(province_code) REFERENCES provinces(code),
        FOREIGN KEY(administrative_unit_id) REFERENCES administrative_units(id)
    );
    """)
    
    # Create indexes for optimization
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_provinces_unit ON provinces(administrative_unit_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_wards_province ON wards(province_code);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_wards_unit ON wards(administrative_unit_id);")
    
    conn.commit()
    
    # 3. Read and execute the SQL file
    print("Reading SQL import data...")
    with open(sql_path, "r", encoding="utf-8") as f:
        sql_content = f.read()
        
    print("Executing SQL data import...")
    try:
        # SQLite's executescript runs everything in a transaction automatically
        cursor.executescript(sql_content)
        conn.commit()
        print("✅ Data imported successfully!")
    except Exception as e:
        conn.rollback()
        print(f"❌ Error during import: {e}")
        sys.exit(1)
        
    # Verify counts
    cursor.execute("SELECT COUNT(*) FROM administrative_regions")
    regions_cnt = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM administrative_units")
    units_cnt = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM provinces")
    provinces_cnt = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM wards")
    wards_cnt = cursor.fetchone()[0]
    
    print("\n--- Import Summary ---")
    print(f"Administrative Regions: {regions_cnt}")
    print(f"Administrative Units  : {units_cnt}")
    print(f"Provinces             : {provinces_cnt}")
    print(f"Wards/Subdivisions    : {wards_cnt}")
    print("----------------------")
    
    conn.close()
    print("Connection closed.")

if __name__ == "__main__":
    main()
