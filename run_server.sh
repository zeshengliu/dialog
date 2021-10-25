# 1. 启动rasa server
python -m rasa run --enable-api --model models/ --port 5005 --endpoints endpoints.yml --credentials credentials.yml --debug &
# 2. 启动action server
python -m rasa run actions --port 5055 --actions actions --debug &
# 3. 启动server.py
python server.py

