# 基于rasa的任务式对话系统

### 1、模型训练

(1) 需要将配置文件补充完成，如下：<br/>
> &ensp; 1) nlu.yml: NLU模块训练文件，包括意图识别和实体抽取需要的文本<br/>
&ensp; 2) stories.yml: Core模块训练文件，主要用于对话策略模型的训练<br/>
&ensp; 3) rules.yml: Core模块训练文件，主要用于对话策略规则的训练<br/>
&ensp; 4) domain.yml: 定义了对话需要用到的意图、实体、槽位、form策略中槽位与实体的
对应关系以及每个意图对应的回复内容<br/>
&ensp; 5) config.yml: 指定模型训练的pipeline，包括指定模型及对应参数，规则<br/>
&ensp; 6) endpoints.yml: 其他需求，包括定义访问新模型，指定tracker存储位置等<br/>

(2) 启动训练脚本
> sh run_train.sh
