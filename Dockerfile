FROM python:3.12-slim

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code and data
COPY . .

# Expose port (Render sets $PORT dynamically)
ENV PORT=8000
EXPOSE 8000

# Start the FastAPI server
CMD ["sh", "-c", "python -m uvicorn gateway.main:app --host 0.0.0.0 --port ${PORT}"]
