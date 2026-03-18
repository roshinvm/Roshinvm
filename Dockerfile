FROM python:3.10

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir streamlit pandas numpy scikit-learn prophet openpyxl

EXPOSE 8501

CMD ["streamlit", "run", "app3.py", "--server.port=8501", "--server.address=0.0.0.0"]