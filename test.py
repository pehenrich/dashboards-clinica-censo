import pyodbc

def get_conn():
    conn_str = (
        "DRIVER={SQL Server};"
        "SERVER=192.168.1.9;"
        "DATABASE=smart;"
        "UID=smart;"
        "PWD=smart@pixeon16;"
    )

    return pyodbc.connect(conn_str)

conn = get_conn()

print("Conectado com sucesso")