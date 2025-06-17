FROM python@sha256:82c07f2f6e35255b92eb16f38dbd22679d5e8fb523064138d7c6468e7bf0c15b

WORKDIR /app

RUN pip install --upgrade pip==25.0.1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH="/app"

CMD ["python", "-m", "src.wt3"]
