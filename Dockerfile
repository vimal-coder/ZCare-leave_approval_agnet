FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose port 8003
EXPOSE 8003

# Command to run the application
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8003"]
