FROM python:3.11-slim
RUN pip install --no-cache-dir matplotlib==3.8.4 numpy==1.26.1 scipy==1.12.0 pillow==10.2.0 python-dotenv==1.0.1 \
    colormath==3.0.0 matplotlib-venn==0.11.10 networkx==3.2.1 scikit-image==0.22.0 squarify==0.4.3
ENV MPLBACKEND=Agg
ENV MPLCONFIGDIR=/tmp/matplotlib
WORKDIR /work
