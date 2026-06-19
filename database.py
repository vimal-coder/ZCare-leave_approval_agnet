import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, DB_MIN_CONN, DB_MAX_CONN

# We initialize a global connection pool
# ThreadedConnectionPool is thread-safe and allows multiple threads to check out connections simultaneously.
_pool = None

def _init_pool():
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(
            minconn=DB_MIN_CONN,
            maxconn=DB_MAX_CONN,
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )

class ConnectionProxy:
    """A proxy wrapper around a psycopg2 connection that returns it to the pool on close() instead of destroying it."""
    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        # Return connection to the pool instead of closing it
        global _pool
        if _pool is not None:
            _pool.putconn(self._conn)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._conn.__exit__(exc_type, exc_val, exc_tb)

def get_connection():
    global _pool
    if _pool is None:
        _init_pool()
    conn = _pool.getconn()
    return ConnectionProxy(conn)

    