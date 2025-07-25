# Use official Python image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set work directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy project files
COPY . .

# Collect static files (optional if using whitenoise or serving static separately)
RUN python manage.py collectstatic --noinput

# Run migrations
RUN python manage.py migrate

# Expose port
EXPOSE 8000

# Start server
CMD ["gunicorn", "instagram_auth.wsgi:application", "--bind", "0.0.0.0:8000"]
