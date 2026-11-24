import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from app.config import env

#with psycopg.connect(env('PG_URI')) as conn:
#	with conn.cursor() as cur:
#		cur.execute('select 1')
#		print(cur.fetchone())

with psycopg.connect(env("PG_URI")) as conn:
    print("connected:", conn.execute("select version()").fetchone()[0].split(",")[0])

# setup() creates the checkpoint tables if they don't exist; safe to run again
with PostgresSaver.from_conn_string(env("PG_URI")) as saver:
    saver.setup()


with psycopg.connect(env("PG_URI")) as conn:
    tables = [r[0] for r in conn.execute(
        "select tablename from pg_tables where tablename like 'checkpoint%' order by 1")]

print("checkpoint tables:", tables)
print("PG SMOKE PASSED" if tables else "PG SMOKE FAILED: no checkpoint tables")