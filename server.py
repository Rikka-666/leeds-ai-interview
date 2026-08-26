import flask
import openai
import base64
from functools import wraps
import os
import time
from werkzeug.security import generate_password_hash,check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from markitdown import MarkItDown
import prompt
import pickle
import ast
import random
import threading
import waitress
import logging
#requirements:flask,openai,markitdown[pptx,docx,xlsx,xls,pdf],waitress
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S')
with open("api_key.txt") as api_key_file:
    API_KEY=api_key_file.read()
AI_BASE_URL="https://api.deepseek.com"
MODEL="deepseek-v4-flash"
LOGIN_OVERDUE=86400 #登陆过期时间 一天86400s
ai_client=openai.OpenAI(api_key=API_KEY,base_url=AI_BASE_URL)
app=flask.Flask(__name__)
app.secret_key=os.urandom(64)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
#session["user_name"] 原始字符串存储的用户名 注意和保存时用的b64格式区分开
dialogue={}
generating_report={}#正在生成的报告
@app.after_request
def log_access(response):
    # 获取用户的真实IP
    user_ip = flask.request.headers.get('X-Forwarded-For')
    if user_ip:
        # 取第一个 IP（最原始客户端）
        real_ip=user_ip.split(',')[0].strip()  
    # 备选：X-Real-IP
    real_ip=flask.request.headers.get('X-Real-IP')
    app.logger.info(f"{real_ip} - {flask.request.method} {flask.request.path} {response.status_code}")
    return response
def login_required(f):#需要登录的页面的前置钩子
    @wraps(f)
    def decorated_func(*args,**kwargs):
        if ("user_name" not in flask.session) or (int(time.time())-int(flask.session["login_time"])>=LOGIN_OVERDUE):
            if flask.request.is_json or flask.request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return flask.jsonify({"status": "error", "message": "未登录或登录已过期"}), 401
            return flask.redirect(flask.url_for("login"))
        return f(*args, **kwargs)
    return decorated_func

def generate_report(dialogue_data,user_name_b64):#生成面试后的评估报告
    global generating_report
    generating_report[user_name_b64]=True
    dialogue_history=dialogue_data["questions_answers_list"]
    for i in range(3):
        with open("user_data\\"+user_name_b64+"\\resume_list.pkl", "rb") as f:
                resume_data=pickle.load(f)
        print("开始评估")
        response=ai_client.chat.completions.create(
            model=MODEL,messages=
            [{"role": "system", "content": prompt.generate_report.format(resume_list=resume_data)},{"role": "user", "content": str(dialogue_history)}],
            stream=False)
        try:
            now_time=int(time.time())
            report={"report":ast.literal_eval(response.choices[0].message.content),
            "generate_time":now_time,"dialogue":dialogue_history}
            with open("user_data\\"+user_name_b64+"\\chat_history\\"+str(now_time)+".pkl","wb") as chat_history_file:
                pickle.dump(report,chat_history_file)
                print("写入文件")
            break
        except Exception as e:
            pass
    del generating_report[user_name_b64]


@app.route("/",methods=["GET"])
def index():
    return flask.render_template("index.html")

@app.route("/static/<file_name>",methods=["GET"])
def static_file(file_name):
    return flask.send_from_directory(app.static_folder,file_name)

@app.route("/login",methods=["GET"])
def login():
    if "user_name" in flask.session and (int(time.time())-int(flask.session["login_time"])<LOGIN_OVERDUE):
        return flask.redirect(flask.url_for("manage"))
    return flask.render_template("login.html")

@app.route("/sign",methods=["GET"])
def sign():
    if "user_name" in flask.session and (int(time.time())-int(flask.session["login_time"])<LOGIN_OVERDUE):
        return flask.redirect(flask.url_for("manage"))
    return flask.render_template("sign.html")

@app.route("/manage",methods=["GET"])
@login_required
def manage():
    username=base64.b64encode(flask.session["user_name"].encode()).decode()
    resume_data=['',True,'','','','','',2026,'','','','','','','','','未上传简历']
    if os.path.exists("user_data\\"+username+"\\resume_list.pkl"):
        with open("user_data\\"+username+"\\resume_list.pkl", "rb") as f:
                resume_data=pickle.load(f)
    report_html_tem="""<div class="record-item">
                    <div class="record-info">
                        <span>生成时间：{report_time}</span>
                    </div>
                    <div class="record-links">
                        <a href="{report_link}">查看原始对话</a>
                    </div>
                </div>"""
    report_html=""
    for i in os.listdir("user_data\\"+username+"\\chat_history"):
        with open("user_data\\"+username+"\\chat_history\\"+i,"rb") as chat_file:
                dialogue_dict=pickle.load(chat_file)
        formatted_time = time.strftime("%Y年%m月%d日 %H:%M", time.gmtime(dialogue_dict["generate_time"]+8 * 3600))
        report_html+=report_html_tem.format(report_time=formatted_time,report_link=flask.url_for('chat_history',report_time=str(dialogue_dict["generate_time"])))
    if generating_report.get(username):
        if_generating="你有正在生成的报告，可稍后刷新查看。"
    else:
        if_generating=""
    return flask.render_template("management.html",resume_data=resume_data,user_name=flask.session["user_name"],record_list=report_html,if_generating=if_generating)

@app.route("/interview",methods=["GET"])
@login_required
def interview():
    global dialogue
    print(dialogue)
    username=base64.b64encode(flask.session["user_name"].encode()).decode()
    user_name=flask.session["user_name"]#注意这里是原始字符串的user_name
    if user_name not in dialogue:
        if os.path.exists("user_data\\"+username+"\\resume_list.pkl"):
            with open("user_data\\"+username+"\\resume_list.pkl","rb") as resume_list_file:
                resume_list=str(pickle.load(resume_list_file)[0:16])
        else:
            return flask.redirect(flask.url_for("manage"))
        dialogue[user_name]={}
        dialogue[user_name]["questions"]=random.randint(10,13)#问题总数随机10-13
        dialogue[user_name]["current_question_count"]=1
        dialogue[user_name]["questions_answers_list"]=[]#包含问题、答案和评价
        dialogue[user_name]["openai_prompt_list"]=[]
        dialogue[user_name]["follow_up_count"]=0
        response=ai_client.chat.completions.create(model=MODEL,messages=
        [{"role":"system","content":prompt.init_interview},{"role":"user","content":resume_list}],temperature=0.0,
        stream=False,extra_body={"thinking": {"type": "enabled"}})
        try:
            dialogue[user_name]["field"]=ast.literal_eval(response.choices[0].message.content)
        except Exception:
            dialogue[user_name]["field"]=["后端", "前端", "人工智能", "云计算", "网络", "游戏"]
        field=set(dialogue[user_name]["field"])
        question_list=[i for i in prompt.questions if set(i["type"])&field]
        chosen_question_list=random.sample(question_list,5)
        chosen_question=""
        for i in range(1,6):
            chosen_question=chosen_question+"[{}]".format(i)+chosen_question_list[i-1]["question"]+"|"+chosen_question_list[i-1]["answer"]+"\n"
        interview_prompt=prompt.interview.format(resume_list=resume_list,chosen_question=chosen_question)
        dialogue[user_name]["openai_prompt_list"].append(
            {"role":"system","content":interview_prompt})
        dialogue[user_name]["openai_prompt_list"].append(
            {"role":"user","content":"@start@"})
        for i in range(3):
            try:
                response=ai_client.chat.completions.create(model=MODEL,messages=
        dialogue[user_name]["openai_prompt_list"],temperature=0.0,
        stream=False)
                next_question_dict=ast.literal_eval(response.choices[0].message.content)
                dialogue[user_name]["openai_prompt_list"].append(response.choices[0].message)
                print(dialogue[user_name]["openai_prompt_list"])
                dialogue[user_name]["questions_answers_list"].append([next_question_dict["next_question"],"",""])
                break
            except Exception:
                pass
    else:
        next_question_dict={"next_question":dialogue[user_name]["questions_answers_list"][-1][0]}
    return flask.render_template("interview.html",question=next_question_dict["next_question"])

@app.route("/chat_history/<report_time>",methods=["GET"])
@login_required
def chat_history(report_time):
    username=base64.b64encode(flask.session["user_name"].encode()).decode()
    if not os.path.exists("user_data\\"+username+"\\chat_history\\"+report_time+".pkl"):
        return "没有这个报告文件",404
    with open("user_data\\"+username+"\\chat_history\\"+report_time+".pkl","rb") as chat_file:
        dialogue_dict=pickle.load(chat_file)
    utc8_struct = time.gmtime(int(report_time)+8 * 3600)
    formatted_time = time.strftime("%Y年%m月%d日 %H:%M", utc8_struct)
    return flask.render_template("report.html",user_name=flask.session["user_name"],generate_time=formatted_time,report_data=dialogue_dict["report"],qa_list=dialogue_dict["dialogue"])
#以下是api
@app.route("/api/login",methods=["POST"])
def api_login():
    data=flask.request.get_json()
    username=base64.b64encode(data.get("username").encode()).decode()
    password=data.get("password")
    if  username in os.listdir("user_data"):
        with open("user_data\\"+username+"\\password.txt") as password_file:
            if check_password_hash(password_file.read().strip(),password):
                flask.session["user_name"]=base64.b64decode(username).decode()
                flask.session["login_time"]=int(time.time())
                return flask.jsonify({'status': 'success', 'message': '验证通过，正在跳转...'}), 200
            else:
                return flask.jsonify({'status': 'error', 'message': '账号或密码错误，请重新输入'}), 401
    else:
        return flask.jsonify({'status': 'error', 'message': '账号或密码错误，请重新输入'}), 401

@app.route("/api/sign",methods=["POST"]) 
def api_sign():
    data=flask.request.get_json()
    username=base64.b64encode(data.get("username").encode()).decode()
    password=data.get("password")
    confirm_password=data.get("confirm_password")
    if password != confirm_password:
        return flask.jsonify({'status': 'error', 'message': '两次输入的密码不一致'}), 401
    if username in os.listdir("user_data"):
        return flask.jsonify({'status': 'error', 'message': '这个账户名已被注册'}), 401
    if password == "":
        return flask.jsonify({'status': 'error', 'message': '密码不能为空'}), 401
    os.mkdir("user_data\\"+username)
    os.mkdir("user_data\\"+username+"\\chat_history")
    with open("user_data\\"+username+"\\password.txt","w") as password_file:
        password_file.write(generate_password_hash(password))
    return flask.jsonify({'status': 'success', 'message': '已成功注册'}), 200

@app.route("/api/logout",methods=["POST"])
@login_required
def api_logout():
    flask.session.clear()
    return flask.jsonify({'status': 'success', 'message': '已成功退出登录'}), 200

@app.route("/api/edit_password",methods=["POST"])
@login_required
def api_edit_password():
    data=flask.request.get_json()
    if data.get("edit_password")!=data.get("confirm_edit_password"):
        return flask.jsonify({'status': 'error', 'message': '两次确认密码不一致'}), 401
    if data.get("edit_password") == '':
        return flask.jsonify({'status': 'error', 'message': '密码不能为空'}), 401
    with open("user_data\\"+base64.b64encode(flask.session["user_name"].encode()).decode()+"\\password.txt") as password_file:
        if not check_password_hash(password_file.read(),data.get("raw_password")):
            return flask.jsonify({'status': 'error', 'message': '原始密码不正确'}), 401
    with open("user_data\\"+base64.b64encode(flask.session["user_name"].encode()).decode()+"\\password.txt","w") as password_file:
        password_file.write(generate_password_hash(data.get("edit_password")))
    return flask.jsonify({'status': 'success', 'message': '修改成功'}), 200

@app.route("/api/upload_resume",methods=["POST"])
@login_required
def api_upload_resume():
    if 'resume' not in flask.request.files:
        return flask.jsonify({'status': 'error', 'message': '未找到文件数据'}), 400
        
    file = flask.request.files['resume']   
    if file.filename == '':
        return flask.jsonify({'status': 'error', 'message': '未选择文件'}), 400
    username =base64.b64encode(flask.session["user_name"].encode()).decode()
    file_path="user_data\\"+username+"\\"+file.filename
    file.save(file_path)
    resume_content=MarkItDown()
    resume_content_text=resume_content.convert(file_path)
    print(resume_content_text.text_content)
    response=ai_client.chat.completions.create(
        model=MODEL,messages=[{"role":"system","content":prompt.read_resume},
        {"role":"user","content":resume_content_text.text_content}],temperature=0.0,
        stream=False,extra_body={"thinking": {"type": "disabled"}})
    with open("user_data\\"+username+"\\resume_list.pkl","wb") as resume_list_file:
        try:
            resume_list=ast.literal_eval(response.choices[0].message.content)
        except Exception as e:
            resume_list=['',True,'','','','','',2026,'','','','','','','','']
            return flask.jsonify({'status': 'error', 'message': 'AI无法读取简历，请重试'}), 400
        resume_list.append(file.filename)
        pickle.dump(resume_list,resume_list_file)  
    return flask.jsonify({'status': 'success', 'message': '文件上传成功'}), 200

@app.route("/api/upload_resume_list",methods=["POST"])
@login_required
def api_upload_resume_list():
    username=base64.b64encode(flask.session["user_name"].encode()).decode()
    data=flask.request.get_json()
    if os.path.exists("user_data\\"+username+"\\resume_list.pkl"):
        with open("user_data\\"+username+"\\resume_list.pkl","rb") as resume_list_file:
            resume_list=pickle.load(resume_list_file)
            if resume_list[16]:
                new_resume_list=data["resume_list"]
                new_resume_list.append(resume_list[16])
            else:
                new_resume_list=data["resume_list"]
                new_resume_list.append("用户手动添加简历")
    else:
        new_resume_list=data["resume_list"]
        new_resume_list.append("用户手动添加简历")
    with open("user_data\\"+username+"\\resume_list.pkl","wb") as resume_list_file:
        pickle.dump(new_resume_list,resume_list_file)
    return flask.jsonify({'status': 'success', 'message': '简历保存成功'}), 200

@app.route("/api/submit_answer",methods=["POST"])
@login_required
def api_submit_answer():
    global dialogue
    user_name=flask.session["user_name"]
    data=flask.request.get_json()
    user_answer=data.get("answer", "")
    if user_name not in dialogue:
        return flask.jsonify({"status": "error", "message": "面试状态异常，请返回上一页重新进入"}), 400
    dialogue[user_name]["questions_answers_list"][dialogue[user_name]["current_question_count"]-1][1]=user_answer
    return_end=False
    if dialogue[user_name]["current_question_count"]==dialogue[user_name]["questions"]:
        dialogue[user_name]["openai_prompt_list"].append(
        {"role": "user", "content": user_answer+"@end@"})
        return_end=True
    elif dialogue[user_name]["follow_up_count"]>=2:
        dialogue[user_name]["openai_prompt_list"].append(
        {"role": "user", "content": user_answer+"@next@"})
        dialogue[user_name]["follow_up_count"]=0
    else:
        dialogue[user_name]["openai_prompt_list"].append(
        {"role": "user", "content": user_answer})
    for i in range(3):
        try:
            response=ai_client.chat.completions.create(model=MODEL,messages=
        dialogue[user_name]["openai_prompt_list"],stream=False)
            next_question_dict=ast.literal_eval(response.choices[0].message.content)
            dialogue[user_name]["openai_prompt_list"].append(response.choices[0].message)
            dialogue[user_name]["questions_answers_list"][-1][2]=next_question_dict["evaluation"]
            if not return_end:
                dialogue[user_name]["questions_answers_list"].append([next_question_dict["next_question"],"",""])
                print(next_question_dict)
            if next_question_dict["next_question"]:
                break
        except Exception:
            pass
    if next_question_dict["action"]=="follow_up":
        dialogue[user_name]["follow_up_count"]+=1
    dialogue[user_name]["current_question_count"]+=1
    if return_end:
        user_data_copy = dialogue.pop(user_name)
        report_thread=threading.Thread(target=generate_report,args=(user_data_copy,base64.b64encode(user_name.encode()).decode()))
        report_thread.start()
        return flask.jsonify({"status": "end"}), 200
    return flask.jsonify({"status": "success","next_question":next_question_dict["next_question"]}), 200


waitress.serve(app,port=81,host="127.0.0.1",threads=4)