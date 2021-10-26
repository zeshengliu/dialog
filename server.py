"""
    server.py
    ~~~~~~~~~

    web server，定义前端调用接口
"""
from flask import Flask, send_from_directory
from flask import request
import requests
import json
import yaml
import re
from copy import deepcopy
import rasa.shared.nlu.training_data.loading as loading
from filesystem import Scaner
from fuzzywuzzy import process
import os

REQUESTED_SLOT = "requested_slot"
MODELS_DIR = "models"

app = Flask(__name__)


# 用于提交post请求
def post(url, data=None):
    data = json.dumps(data, ensure_ascii=False).encode(encoding="utf-8")
    res = requests.post(url=url, data=data, headers={'Content-Type': 'application/json'})
    res = json.loads(res.text)
    return res


def replyProcess(reply):
    temp_reply = deepcopy(reply)
    left = re.finditer("\[", temp_reply)
    right = re.finditer("\]", temp_reply)
    pos_list = list(zip(list(map(lambda p: p.start(), left)), list(map(lambda p: p.end(), right))))
    if not pos_list:
        return reply
    for pos in pos_list:
        word = sorted(eval(temp_reply[pos[0]:pos[1]]), key=lambda p: len(p), reverse=True)[0]
        reply = reply.replace(temp_reply[pos[0]:pos[1]], word)
    return reply


def intentSlotsEntities(intent):
    domain_file = "domain.yml"
    with open(domain_file, 'r') as fr:
        forms = yaml.load(fr, Loader=yaml.FullLoader)["forms"]
        form_name = intent + "_form"
        entities, slots = set(), set()
        for key, value in forms[form_name]["required_slots"].items():
            slots.add(key)
            entities.add(value[0]["entity"])
    return list(slots), list(entities)


def isGetAllSlots(tracker, intent):
    intent_slots = intentSlotsEntities(intent)[0]
    tracker_slots = tracker["slots"]
    flag = True
    for slot in intent_slots:
        flag = flag and (tracker_slots[slot] is not None)
    return flag


def messagePretreatment(query):
    nlu_file = 'data/nlu.yml'
    try:
        td = loading.load_data(nlu_file, language='zh')
        all_d = json.loads(td.nlu_as_json(indent=2))['rasa_nlu_data']['common_examples']
        choices = list(map(lambda p: p["text"], all_d))
        return process.extractOne(query, choices)[1]
    except FileNotFoundError as err:
        raise err


# 是否达到追问次数
def isMaxAskTimes(required_slot, events, max_time=3):
    count = 0
    if len(events) < max_time:
        return False
    for e in events:
        if e["event"] == "slot" and e["name"] == REQUESTED_SLOT and e["value"] == required_slot:
            count += 1
    if count > max_time:
        return True
    else:
        return False


def messageValid(message, entities):
    message_score = messagePretreatment(message)
    # 不包含有用信息
    if message_score < 55 and not entities:
        return False
    return True


def use_rule(data, conversation_id):
    intent = data["intent"]
    out_msg = {"state": None, "result": {}}
    user_data = {
        "sender": "user",
        "text": data["text"],
        "parse_data": {
            "intent": {
                "confidence": 1.0,
                "name": intent
            },
            "entities": [],
            "text": data["text"]
        }
    }
    intent_data = {
        "name": data["intent"],
    }
    for entity in data["entities"]:
        user_data["parse_data"]["entities"].append({
                "entity": entity[1],
                "value": entity[0]
            })
    # 执行某个动作的url
    action_url = "http://localhost:5005/conversations/{}/execute".format(conversation_id)
    # 触发意图
    intent_url = "http://localhost:5005/conversations/{}/trigger_intent".format(conversation_id)
    # 提交消息，不触发nlu
    message_url = f"http://localhost:5005/conversations/{conversation_id}/messages"

    # 用于预测next_action
    predict_url = f"http://localhost:5005/conversations/{conversation_id}/predict"

    set_slot_action, reset_slot_action = {"name": "action_set_slot"}, {"name": "action_reset_slot"}
    post(message_url, user_data)
    post(action_url, set_slot_action)
    tracker = post(intent_url, data=intent_data)
    messages = tracker["messages"]
    while not messages:
        tracker = post(intent_url, data=intent_data)
        messages = tracker["messages"]
    resInfo = post(predict_url)
    action_name, tracker = resInfo["scores"][0], deepcopy(resInfo["tracker"])
    if intent == "打招呼" or (intent != "打招呼" and isGetAllSlots(intent=intent, tracker=tracker)):
        post(action_url, reset_slot_action)
    out_msg["state"] = 1
    out_msg["result"]["intent"] = user_data["parse_data"]["intent"]
    # print(tracker)
    # out_msg["result"]["intent"] = tracker["latest_message"]["intent"]
    out_msg["result"]["entities"] = user_data["parse_data"]["entities"]
    out_msg["result"]["slots"] = tracker["slots"]
    out_msg["result"]["next_action"] = action_name
    out_msg["result"]["reply"] = replyProcess(messages[0]["text"])
    return out_msg


def downloadFile(path):
    return send_from_directory(os.path.dirname(path), os.path.basename(path), as_attachment=True,
                               attachment_filename=os.path.basename(path))


@app.route('/<path:path>', methods=['GET'])
def hotUpDate(path):
    fetch_latest = '@latest' in path
    real_path = os.path.join(MODELS_DIR, path.replace('@latest', ''))
    if not os.path.exists(real_path):
        return 'Not Found', 404

    if os.path.isdir(real_path):
        if fetch_latest:
            latest_entry = Scaner(real_path).latest_entry
            if not latest_entry:
                return 'No Models Found', 404
            # print(latest_entry.path)
            return downloadFile(latest_entry.path)
    else:
        return downloadFile(real_path)


@app.route('/query', methods=['GET', 'POST'])
def webToBot():
    """
    前端调用接口
        路径：/ai
        请求方式：GET、POST
        请求参数：content
    :return: response rasa响应数据
    """
    content = request.args.get('text')
    user_id = request.args.get('userid')
    sys_msg = {
        "status": None,
        "text": [],
        "attached":
            {
                "task": {},
                "faq": {},
            }
    }
    if content is None:
        return '输入为空，请您重新输入！'

    # 任务式对话结果
    task_response = requestTaskBotServer(user_id, content)
    state = task_response.pop("state")
    if state == 1:
        sys_msg["status"] = 1030
        sys_msg["attached"]["task"] = task_response.copy()
        sys_msg["text"].append(task_response["result"]["reply"])
        return json.dumps(sys_msg, ensure_ascii=False)
    else:
        sys_msg["status"] = 1000
        sys_msg["text"] = task_response["result"]["reply"]
        return json.dumps(sys_msg, ensure_ascii=False)


def requestTaskBotServer(userid, content):
    """
        访问rasa服务
    :param userid: 用户id
    :param content: 自然语言文本
    :return:  json格式响应数据
    """
    # 利用rasa处理
    params = {'sender': userid, 'message': content}
    user_data = {"text": content, "message_id": userid}
    out_msg = {"state": None, "result": {}}
    # 获取tracker的url
    tracker_url = "http://localhost:5005/conversations/{}/tracker".format(userid)

    # 执行某个动作的url
    action_url = "http://localhost:5005/conversations/{}/execute".format(userid)

    # rasa使用rest channel
    rasa_url = "http://localhost:5005/webhooks/rest/webhook"

    # 获取message的解析结果
    parse_url = "http://localhost:5005/model/parse"

    # 用于预测next_action
    predict_url = f"http://localhost:5005/conversations/{userid}/predict"

    # 获取提交message前的tracker
    lasted_tracker = json.loads(requests.get(tracker_url).text)
    lasted_intent = lasted_tracker['latest_message']['intent']

    # message解析
    parse_res = post(parse_url, data=user_data)
    entities = parse_res["entities"]
    cur_intent = parse_res["intent"]
    if not lasted_intent:
        # 此时为用户第一次对话
        if messageValid(content, entities):
            messages = post(rasa_url, data=params)
            if not messages:
                out_msg["state"] = 0
                out_msg["result"]["reply"] = "发送的信息无效，已为您转人工处理！"
                # 对话重置
                action_data = {"name": "action_reset_slot"}
                post(action_url, action_data)
                return out_msg
            resInfo = post(predict_url)
            action_name, tracker = resInfo["scores"][0], deepcopy(resInfo["tracker"])
            out_msg["state"] = 1
            out_msg["result"]["intent"] = tracker["latest_message"]["intent"]
            out_msg["result"]["entities"] = entities
            out_msg["result"]["slots"] = tracker["slots"]
            for key, val in out_msg["result"]["slots"].items():
                if isinstance(val, list):
                    val_len = list(map(len, val))
                    max_index = val_len.index(max(val_len))
                    out_msg["result"]["slots"][key] = val[max_index]
                else:
                    continue
            out_msg["result"]["next_action"] = action_name
            out_msg["result"]["reply"] = replyProcess(messages[0]["text"])
            return out_msg
        else:
            out_msg["state"] = 0
            out_msg["result"]["reply"] = "发送的信息无效，已为您转人工处理！"
            # 对话重置
            action_data = {"name": "action_reset_slot"}
            post(action_url, action_data)
            return out_msg
    else:
        # 意图未变化
        if cur_intent["name"] == lasted_intent["name"]:
            print("消息提交:", content)
            messages = post(rasa_url, data=params)
            if not messages:
                print("消息为空")
                required_slot = lasted_tracker["slots"][REQUESTED_SLOT]
                if required_slot is not None:
                    if isMaxAskTimes(required_slot=required_slot, events=lasted_tracker["events"]):
                        # 对话重置
                        action_data = {"name": "action_reset_slot"}
                        post(action_url, action_data)
                        out_msg["state"] = 0
                        out_msg["result"]["reply"] = "已经达到最大追问次数，已为您转人工处理！"
                        return out_msg
                    else:
                        action_name = f"utter_ask_{required_slot}"
                        action_data = {"name": action_name}
                        messages = post(action_url, action_data)["messages"]
                        if not messages:
                            out_msg["state"] = 0
                            out_msg["result"]["reply"] = "发送的信息无效，已为您转人工处理！"
                            # 对话重置
                            action_data = {"name": "action_reset_slot"}
                            post(action_url, action_data)
                            return out_msg
                        post(action_url, data={"name": "action_ask_slot"})
                        out_msg["state"] = 1
                        out_msg["result"]["intent"] = lasted_tracker["latest_message"]["intent"]
                        out_msg["result"]["entities"] = entities
                        out_msg["result"]["slots"] = lasted_tracker["slots"]
                        for key, val in out_msg["result"]["slots"].items():
                            if isinstance(val, list):
                                val_len = list(map(len, val))
                                max_index = val_len.index(max(val_len))
                                out_msg["result"]["slots"][key] = val[max_index]
                            else:
                                continue
                        out_msg["result"]["next_action"] = {"name": "action_ask_slot", "score": 1.0}
                        out_msg["result"]["reply"] = replyProcess(messages[0]["text"])
                        return out_msg
                else:
                    # 清空槽位信息
                    action_data = {"name": "action_reset_slot"}
                    post(action_url, action_data)
                    messages = post(rasa_url, data=params)
                    if not messages:
                        out_msg["state"] = 0
                        out_msg["result"]["reply"] = "发送的信息无效，已为您转人工处理！"
                        # 对话重置
                        action_data = {"name": "action_reset_slot"}
                        post(action_url, action_data)
                        return out_msg
                    resInfo = post(predict_url)
                    action_name, tracker = resInfo["scores"][0], resInfo["tracker"]
                    out_msg["state"] = 1
                    out_msg["result"]["intent"] = tracker["latest_message"]["intent"]
                    out_msg["result"]["entities"] = entities
                    out_msg["result"]["slots"] = tracker["slots"]
                    for key, val in out_msg["result"]["slots"].items():
                        if isinstance(val, list):
                            val_len = list(map(len, val))
                            max_index = val_len.index(max(val_len))
                            out_msg["result"]["slots"][key] = val[max_index]
                        else:
                            continue
                    out_msg["result"]["next_action"] = action_name
                    out_msg["result"]["reply"] = replyProcess(messages[0]["text"])
                    return out_msg
            resInfo = post(predict_url)
            action_name, tracker = resInfo["scores"][0], deepcopy(resInfo["tracker"])
            required_slot = tracker["slots"][REQUESTED_SLOT]
            if required_slot is not None:
                if isMaxAskTimes(required_slot=required_slot, events=tracker["events"]):
                    # 对话重置
                    action_data = {"name": "action_reset_slot"}
                    post(action_url, action_data)
                    out_msg["state"] = 0
                    out_msg["result"]["reply"] = "已经达到最大追问次数，已为您转人工处理！"
                    return out_msg
            out_msg["state"] = 1
            out_msg["result"]["intent"] = tracker["latest_message"]["intent"]
            out_msg["result"]["entities"] = entities
            out_msg["result"]["slots"] = tracker["slots"]
            for key, val in out_msg["result"]["slots"].items():
                if isinstance(val, list):
                    val_len = list(map(len, val))
                    max_index = val_len.index(max(val_len))
                    out_msg["result"]["slots"][key] = val[max_index]
                else:
                    continue
            out_msg["result"]["next_action"] = action_name
            out_msg["result"]["reply"] = replyProcess(messages[0]["text"])
            if isGetAllSlots(tracker, cur_intent["name"]):
                action_data = {"name": "action_reset_slot"}
                post(action_url, action_data)
            return out_msg
        else:
            if entities and (set(list(map(lambda p: p["entity"], entities))) &
                             set(intentSlotsEntities(lasted_intent["name"])[1])):
                messages = post(rasa_url, data=params)
                resInfo = post(predict_url)
                action_name, tracker = resInfo["scores"][0], deepcopy(resInfo["tracker"])
                required_slot = lasted_tracker["slots"][REQUESTED_SLOT]
                if isMaxAskTimes(required_slot=required_slot, events=tracker["events"]):
                    # 对话重置
                    action_data = {"name": "action_reset_slot"}
                    post(action_url, action_data)
                    out_msg["state"] = 0
                    out_msg["result"]["reply"] = "已经达到最大追问次数，已为您转人工处理！"
                    return out_msg
                out_msg["state"] = 1
                out_msg["result"]["intent"] = tracker["latest_message"]["intent"]
                out_msg["result"]["entities"] = entities
                out_msg["result"]["slots"] = tracker["slots"]
                for key, val in out_msg["result"]["slots"].items():
                    if isinstance(val, list):
                        val_len = list(map(len, val))
                        max_index = val_len.index(max(val_len))
                        out_msg["result"]["slots"][key] = val[max_index]
                out_msg["result"]["next_action"] = action_name
                out_msg["result"]["reply"] = replyProcess(messages[0]["text"])
                if isGetAllSlots(tracker, lasted_intent["name"]):
                    action_data = {"name": "action_reset_slot"}
                    post(action_url, action_data)
                return out_msg
            required_slot = lasted_tracker["slots"][REQUESTED_SLOT]
            if isMaxAskTimes(required_slot=required_slot, events=lasted_tracker["events"]):
                # 对话重置
                action_data = {"name": "action_reset_slot"}
                post(action_url, action_data)
                out_msg["state"] = 0
                out_msg["result"]["reply"] = "已经达到最大追问次数，已为您转人工处理！"
                return out_msg
            else:
                action_name = f"utter_ask_{required_slot}"
                action_data = {"name": action_name}
                messages = post(action_url, action_data)["messages"]
                while not messages:
                    messages = post(action_url, action_data)["messages"]
                post(action_url, data={"name": "action_ask_slot"})
                if not messages:
                    out_msg["state"] = 0
                    out_msg["result"]["reply"] = "发送的信息无效，已为您转人工处理！"
                    # 对话重置
                    action_data = {"name": "action_reset_slot"}
                    post(action_url, action_data)
                    return out_msg
                out_msg["state"] = 1
                out_msg["result"]["intent"] = lasted_tracker["latest_message"]["intent"]
                out_msg["result"]["entities"] = entities
                out_msg["result"]["slots"] = lasted_tracker["slots"]
                for key, val in out_msg["result"]["slots"].items():
                    if isinstance(val, list):
                        val_len = list(map(len, val))
                        max_index = val_len.index(max(val_len))
                        out_msg["result"]["slots"][key] = val[max_index]
                    else:
                        continue
                out_msg["result"]["next_action"] = {"name": "action_ask_slot", "score": 1.0}
                out_msg["result"]["reply"] = replyProcess(messages[0]["text"])
                return out_msg


if __name__ == '__main__':
    webIp = '127.0.0.1'
    webPort = '8088'
    print("###webIp={}, webPort={}###".format(webIp, webPort))
    # 启动服务，开启多线程、debug模式
    # 浏览器访问curl http://127.0.0.1:8088/query?userid=1\&text=买手机
    app.run(host=webIp, port=webPort, threaded=True)
