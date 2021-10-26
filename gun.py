# encoding=utf-8
import multiprocessing
import gevent.monkey
gevent.monkey.patch_all()

# 服务地址（address:port）
bind = "127.0.0.1:8088"
# 启动进程数量
workers = 10
threads = 8
worker_class = 'gevent'