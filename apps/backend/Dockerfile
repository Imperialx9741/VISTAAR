FROM python:3.12-slim

# Prevent Python from writing .pyc files and buffer output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Copy configuration and project files
COPY pyproject.toml .
COPY README.md .
COPY src/ ./src/

# Install the application and its dependencies
RUN pip install --no-cache-dir .

EXPOSE 8000

# Run Uvicorn server
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
