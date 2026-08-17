import ibm_db
from config import Config

def db2_connect():
    dsn = (
        f"DATABASE={Config.DB_NAME};"
        f"HOSTNAME={Config.DB_HOST};"
        f"PORT={Config.DB_PORT};"
        "PROTOCOL=TCPIP;"
        f"UID={Config.DB_USER};"
        f"PWD={Config.DB_PASSWORD};"
    )
    try:
        conn = ibm_db.connect(dsn, "", "")
        return conn
    except Exception as e:
        print("DB2 Connection Error:", e)
        return None