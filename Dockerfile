FROM python:3.9-slim-bullseye
RUN apt update \
    && apt-get install --yes locales \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && sed -i -e 's/# ru_RU.UTF-8 UTF-8/ru_RU.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen
ENV LANG=ru_RU:UTF-8 \
    LANGUAGE=ru_RU:ru \
    LC_LANG=ru_RU.UTF-8 \
    LC_ALL=ru_RU.UTF-8 \
    TZ=Europe/Moscow
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /tg_bot
COPY . .
RUN /usr/local/bin/python3 -m pip install --no-cache-dir --upgrade pip \ 
    && pip3 install --no-cache-dir -r requirements.txt \
    && rm requirements.txt
ENV LANG=ru_RU:UTF-8
CMD ["python3", "main.py"]