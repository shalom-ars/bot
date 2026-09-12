import sqlite3
import pandas as pd

def run_audit():
    try:
        conn = sqlite3.connect('../data/bot.db')
        
        print("==================================================")
        print("DATABASE AUDIT REPORT")
        print("==================================================")

        tables = ['markets', 'market_snapshots', 'signals', 'trades', 'positions']
        
        for table in tables:
            try:
                count = pd.read_sql_query(f"SELECT COUNT(*) as c FROM {table}", conn).iloc[0]['c']
                print(f"Table '{table}' -> COUNT(*): {count}")
            except Exception as e:
                print(f"Table '{table}' -> Error: {e}")
        
        print("\n--- markets table detail ---")
        try:
            dist_cond = pd.read_sql_query("SELECT COUNT(DISTINCT condition_id) as c FROM markets", conn).iloc[0]['c']
            dist_tok = pd.read_sql_query("SELECT COUNT(DISTINCT token_id) as c FROM markets", conn).iloc[0]['c']
            dist_mid = pd.read_sql_query("SELECT COUNT(DISTINCT market_id) as c FROM markets", conn).iloc[0]['c']
            print(f"COUNT(DISTINCT condition_id): {dist_cond}")
            print(f"COUNT(DISTINCT token_id): {dist_tok}")
            print(f"COUNT(DISTINCT market_id): {dist_mid}")
            
            # Null rates
            total = pd.read_sql_query("SELECT COUNT(*) as c FROM markets", conn).iloc[0]['c']
            null_cond = pd.read_sql_query("SELECT COUNT(*) as c FROM markets WHERE condition_id IS NULL", conn).iloc[0]['c']
            null_tok = pd.read_sql_query("SELECT COUNT(*) as c FROM markets WHERE token_id IS NULL", conn).iloc[0]['c']
            print(f"NULL condition_id: {null_cond} / {total} ({(null_cond/total*100):.2f}%)")
            print(f"NULL token_id: {null_tok} / {total} ({(null_tok/total*100):.2f}%)")
            
        except Exception as e:
            print("Error in markets detail:", e)

        print("\n--- market_snapshots table detail ---")
        try:
            dist_sym = pd.read_sql_query("SELECT COUNT(DISTINCT symbol) as c FROM market_snapshots", conn).iloc[0]['c']
            dist_mid = pd.read_sql_query("SELECT COUNT(DISTINCT market_id) as c FROM market_snapshots", conn).iloc[0]['c']
            print(f"COUNT(DISTINCT token_id/symbol): {dist_sym}")
            print(f"COUNT(DISTINCT market_id): {dist_mid}")
            
            # Null rates
            total_s = pd.read_sql_query("SELECT COUNT(*) as c FROM market_snapshots", conn).iloc[0]['c']
            null_p = pd.read_sql_query("SELECT COUNT(*) as c FROM market_snapshots WHERE price IS NULL", conn).iloc[0]['c']
            null_b = pd.read_sql_query("SELECT COUNT(*) as c FROM market_snapshots WHERE bid IS NULL", conn).iloc[0]['c']
            null_a = pd.read_sql_query("SELECT COUNT(*) as c FROM market_snapshots WHERE ask IS NULL", conn).iloc[0]['c']
            null_sp = pd.read_sql_query("SELECT COUNT(*) as c FROM market_snapshots WHERE spread IS NULL", conn).iloc[0]['c']
            
            print(f"NULL price: {null_p} / {total_s} ({(null_p/total_s*100):.2f}%)")
            print(f"NULL bid: {null_b} / {total_s} ({(null_b/total_s*100):.2f}%)")
            print(f"NULL ask: {null_a} / {total_s} ({(null_a/total_s*100):.2f}%)")
            print(f"NULL spread: {null_sp} / {total_s} ({(null_sp/total_s*100):.2f}%)")
        except Exception as e:
            print("Error in market_snapshots detail:", e)
            
        conn.close()
    except Exception as e:
        print("Fatal error:", e)

run_audit()
