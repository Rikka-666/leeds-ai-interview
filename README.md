# leeds-ai-interview
**This is a competition entry by Rikka-666 from SouthWest Jiaotong University-Leeds joint school, DO NOT use it in production environment**.<br>
这是学生参加西南交通大学利兹学院的比赛作品，请不要将它部署到生产环境中

# 2026 年利兹科技月AI模拟面试与能力提升软件 设计文档
## 软件设计技术栈
后端技术：后端web服务器使用python语言开发，使用flask框架设计，配合静态的
html 页面和api路由实现核心上传简历，对话功能。使用常用的session与cookie实现用户的
登录功能。用户的原始简历，对话历史记录等数据没有采用数据库，而是直接按用户名分文
件夹存储。解析后的简历数据，每次模拟面试的对话、评价得分等内容使用pickle库存储。
用户的密码计算为采用加盐的哈希值存储到服务器上。核心的AI模型采用Deepseek-v4
flash，使用官方的api（即api.deepseek.com）， api-key 写入到单独的 api_key.txt 文件存储到
服务器上，服务端运行时读取apikey进程序。pdf，word等简历文件使用开源python库
Markitdown 读取并转换为markdown格式，再传输给大模型分析。由于服务器上还部署了一
些其他的个人项目，因此使用了nginx反代理到/ai_interview路径下。 <br>
前端技术：前端采用简单的静态网页，使用HTML, CSS与JavaScript编写，数据可视化
部分使用了JS库ECharts。<br>
## 功能流程设计
程序包含了完成的用户登录、简历输入解析、用户画像生成、连续文字面试及追问逻辑
等功能。.<br>
### 简历解析与用户画像构建 
用户在管理后台上传简历文件（支持PDF、Word、Excel等多种格式）。在后端
/api/upload_resume 接口中，系统首先调用第三方库MarkItDown对上传的文件进行纯文本提
取。 随后，系统调用AI模型，并使用严格的系统提示词prompt.read_resume，强制要求大
模型从文本中提取姓名、学历、主修课程、掌握技能、核心项目经历等信息，并按照严格的
数据类型生成长度为16的列表。代码中使用了try…except块结合ast.literal_eval()解析返回
结果。若解析失败，系统会触发降级方案，自动生成一个带默认值的16项空列表（如
['',True,'','','','','',2026,...]），确保后续流程不会因格式错误而中断。<br> 
### 题库动态匹配与面试开始 
本阶段系统将根据生成的简历画像，从本地知识库中动态抽取匹配的基础知识点，构建
专属面试考卷。用户点击“开始模拟面试”后，系统在后台进行题库匹配，完成初始化后跳
转至问答界面。在/interview 路由中，系统首先通过prompt.init_interview让 AI模型阅读序
列化后的简历列表，判定候选人擅长的计算机领域（如后端、前端、人工智能等）。系统内置
了包含50道带详细解答的计算机基础知识题库prompt.questions。代码利用交集操作 
set(i["type"])&field 筛选出与候选人领域匹配的题库子集，并使用random.sample()随机抽取
5 道必答题。最终，抽取的题目与原始简历列表会被共同格式化注入到prompt.interview的
System Prompt 中。系统会在上下文中记录这5个特定问题，并使用@start@标记提示AI模型
正式启动面试。<br>
### 连续面试循环 
这是系统的核心逻辑层。系统需要记住前序对话，控制面试节奏，并在深度追问与推进
流程之间保持平衡。用户在前端提交回答，系统展示“正在评估”，随后返回下一个问题或
对这个问题的追问。后端通过全局字典dialogue[user_name]["openai_prompt_list"]来保存当
前用户的完整的上下文消息列表，确保多轮对话具备记忆能力。在/api/submit_answer 接口
中，系统强制大模型返回结构化的字典（包含evaluation评价、action动作策略、
next_question 下一题），并使用一套自定义的Tag标识符（使用@@包裹的特殊标记）进行流程
控制。为了防止 AI模型对某一项目细节无限追问，系统设计了follow_up_count计数器。当
系统检测到连续追问次数达到2次（follow_up_count>= 2）时，会在用户的下一次回答末尾
隐式追加@next@标记，强制 AI模型停止追问并推进到下一个全新问题。当问题计数器
current_question_count 达到预设的总题数时，系统会追加@end@标记，要求AI模型终止面试
输出。  <br>
### 评估生成与多维数据保存 
在面试结束后，系统需要对全程问答进行评估，并在不阻塞用户交互的前提下生成专业
的可视化报告。面试结束后前端自动跳转回主页，后台隐式生成报告，生成完毕后用户可在
记录列表中查看雷达图与诊断报告。系统在结束面试后，采用 
threading.Thread(target=generate_report, ...)开启线程处理报告生成，主线程立刻向前端返
回{"status":"end"}。在异步线程中，系统将完整对话实录dialogue_history与简历提交给 AI
模型，并通过prompt.generate_report 要求 AI 返回字段（包含知识掌握、项目深度等5项分
数，以及strength、weakness 等文本评估）。最终，评估数据通过 pickle.dump以时间戳命名
保存面试记录到user_data的对应目录下，供用户查看。<br>
## 知识库来源与构建方法
题库来自CSDN论坛，【2026年3月】最新计算机专业面试八股文（全体系总结），原文
链接是<br>https://blog.csdn.net/qq_45914609/article/details/158659329<br>所有题目的由 Gemini 
3.1pro 生成答案并分类，最后生成了一个很长的列表questions，保存在prompt.py中，每个
题目遵循以下字典格式：{"type":[（问题的类型）],"question": "（问题）","answer": "（答案）
"}，"type"字段是该问题涉及的计算机方向的列表，包含后端、前端、人工智能、云计算、网
络、游戏中的一个或几个。在读取用户的简历时，即会判断用户接触过哪些计算机方向，在
面试时会根据这些方向抽取对应题目。 <br>
## 评分反馈设计
面试结束后，后台会根据回答情况对用户从知识掌握, 项目深度, 回答逻辑, 表达完整, 
岗位匹配等方面进行打分，并按条生成用户优点，不足以及提升建议。<br>
## AI 工具使用情况
这个项目使用了Gemini 3.1pro辅助开发。所有静态的html文件以及CSS代码都由
Gemini 生成，其他的包括Javascript代码，后台web服务器的python代码等都由本人编
写，Gemini在寻找代码问题及修改方面提供了多次的帮助。 <br>
网站主页上三幅示意性的图片由Gemini Nano Banana 2模型生成。 <br>
所有由AI生成的代码都经过检查，并且经过修改达到了格式的统一。<br>
## API key 保存情况 
API key 没有存储到服务端主文件server.py中，而是保存在相同目录的api_key.txt文
件中，运行时服务端会从这个文件中读取API key并保存在内存中。 <br> 
api_key.txt 没有被上传到Github仓库。 <br>
## 网站部署情况
这个项目的网站被部署到个人的云服务器上（阿里云成都，2核2G，Windows 
server2019 图形界面版），通过nginx反代理到/ai_interview路径下，访问网站的完整地址
是：<br>https://8.137.182.19/ai_interview/<br>同时可以从这个页面上跳转到Github仓库，下
载演示视频和这个设计文档。 <br>
如果您在访问网站时出现问题，或者在使用时遇到了非重启服务端不可的问题，非常抱
歉，您可以尝试本地部署。 <br>
本地部署步骤： <br>
1. 要求Windows10，11，Windows server2019,2022 或 2025，Python 安装 3.12 或更
高版本。 <br>
2. 运行命令 <br>
pip install flask <br>
pip install openai <br>
pip install markitdown[pptx,docx,xlsx,xls,pdf] <br>
pip install waitress <br>
3. 安装Microsoft Visual C++ Redistributable vc_redist.x64.exe <br>
4. 在server.py 相同路径创建文件api_key.txt，并且在其中写入deepseek的api<br>
密钥 <br>
5. 双击运行server.py <br>
6. 访问http://127.0.0.1:81/<br>
7. 已有一个用户名为：1，密码：1
