import os
import configparser
from dotenv import load_dotenv

# Load env variables from .env if present, overriding any existing environment variables
load_dotenv(override=True)

# Initialize configparser
config = configparser.ConfigParser()
config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.ini')

if os.path.exists(config_path):
    config.read(config_path)

def get_setting(section, option, default=None):
    # 1. Check environment variables first (usually uppercase)
    env_val = os.getenv(option.upper()) or os.getenv(option)
    if env_val is not None:
        val = env_val.strip().strip('"').strip("'")
        if val != "":
            return val
    
    # 2. Check config.ini
    if config.has_section(section) and config.has_option(section, option):
        val = config.get(section, option)
        if val is not None:
            val = val.strip().strip('"').strip("'")
            if val != "":
                return val
        
    return default

# Database configuration
DB_HOST = get_setting('database', 'DB_HOST', 'localhost')
DB_PORT = get_setting('database', 'DB_PORT', '5432')
DB_NAME = get_setting('database', 'DB_NAME', 'zcare_leave_db')
DB_USER = get_setting('database', 'DB_USER', 'postgres')
DB_PASSWORD = get_setting('database', 'DB_PASSWORD', '')
DB_MIN_CONN = int(get_setting('database', 'DB_MIN_CONN', '1'))
DB_MAX_CONN = int(get_setting('database', 'DB_MAX_CONN', '15'))

# Email configuration
EMAIL_SENDER = get_setting('email', 'EMAIL_SENDER', 'vimaldj001@gmail.com')
EMAIL_PASSWORD = get_setting('email', 'EMAIL_PASSWORD', '')
SMTP_HOST = get_setting('email', 'SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT = int(get_setting('email', 'SMTP_PORT', '587'))

# App / LLM configuration
APP_BASE_URL = get_setting('app', 'BASE_URL') or get_setting('app', 'APP_BASE_URL', 'http://127.0.0.1:8000')
GROQ_API_KEY = get_setting('app', 'GROQ_API_KEY', '')
GROQ_MODEL = get_setting('app', 'GROQ_MODEL', 'llama-3.3-70b-versatile')
DEFAULT_MANAGER_EMAIL = get_setting('app', 'DEFAULT_MANAGER_EMAIL', 'manager@zcare.com')
