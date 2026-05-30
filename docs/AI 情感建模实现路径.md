# 人工智能代理中的情感建模：心理学基础、计算架构与多模态实现

## 1. 情感计算与人工智能代理的演进

在人工智能（AI）与人机交互（HCI）的演进历程中，实现机器对人类情感的理解、模拟与响应一直被视为通向通用人工智能（AGI）的关键里程碑。这一跨学科领域被称为情感计算（Affective Computing），最初由Rosalind Picard于1995年提出，旨在开发能够识别、解释、处理和模拟人类情感的计算系统与设备1。早期的对话系统（如Eliza）仅仅依赖于简单的模式匹配和硬编码的规则来触发用户的投射心理，这种现象后来被称为“Eliza效应”，即人类极易对呈现出哪怕极其微弱的交互反馈的机器产生深厚的情感依恋，甚至将其拟人化3。然而，这种基于规则的伪装在面对长期、多轮次的复杂交互时会迅速暴露出其认知局限性。

随着2026年大型语言模型（LLMs）、具身智能（Embodied AI）以及多模态感知技术的突破，人工智能代理（AI Agents）的角色已经从单纯的交易型信息处理器转变为关系型伙伴（Relational Partners）5。现代AI代理不再仅仅通过词法特征提取单一的情感标签，而是依托于深度的内部情感状态架构、复杂的神经符号双重治理系统，以及高度灵敏的多模态特征对齐技术，来实现所谓的“机器集成关系适应”（Machine-Integrated Relational Adaptation, MIRA）5。这种适应性要求系统不仅能在孤立的对话回合中识别愤怒或喜悦，还必须能够跨会话保持记忆的连续性，根据用户的心理暗示动态调整自身的个性参数、生成富含同理心的自然语言，并通过虚拟化身（Avatars）的面部肌肉融合变形与语音韵律将情感具象化地渲染出来7。

本报告旨在详尽、深入地剖析情感建模在现代人工智能代理中的实现路径。分析将从情感的心理学与认知科学基础理论切入，逐步深入至代理内部状态的计算架构、基于多模态融合的感知网络、通过对齐算法优化的情感生成机制，以及最终的语音与视觉表达渲染技术。此外，报告还将探讨伴随该技术商业化落地而产生的跨文化适应性挑战、隐私伦理风险以及以《欧洲联盟人工智能法案》（EU AI Act）为代表的全球监管框架10。

## 2. 情感建模的心理学与认知科学基础

任何计算情感模型的构建都必须植根于成熟的心理学与认知科学理论。如果缺乏结构化的情感分类学，AI系统将无法对异构的输入数据进行可靠的映射，也无法生成符合人类心理预期的连贯反馈。目前，情感计算领域主要依赖四种基础理论框架来指导算法的设计与特征空间的划分：离散分类理论、维度表示理论、认知评估理论以及人格特质映射模型1。

### 2.1 离散情绪的分类理论

分类理论（Categorical Theories）假设人类情感可以被划分为一组普遍存在的、离散的基本类别。在这一领域中，最具影响力的理论是Paul Ekman提出的“基本情绪”理论1。该理论最初确认了六种跨文化普遍认可的基本情感：快乐、悲伤、愤怒、恐惧、惊讶和厌恶13。Ekman的模型不仅为心理学提供了基准，更直接催生了面部动作编码系统（Facial Action Coding System, FACS）的诞生。FACS通过对人类面部肌肉群的解剖学分析，将每一种离散情绪分解为特定的动作单元（Action Units, AUs）组合，从而为计算机视觉算法识别面部表情提供了数学上可计算的客观物理描述13。

在Ekman的基础上，Robert Plutchik提出了更为复杂的心理进化理论及其著名的“情感轮”（Wheel of Emotions）14。Plutchik的模型确定了八种主要情感，并将其排列为对立的两极（例如：快乐与悲伤对立，信任与厌恶对立，恐惧与愤怒对立，惊讶与期待对立）14。该模型在计算实现上的优势在于引入了强度（Intensity）向量与组合（Combinations）机制：随着情感向轮盘中心移动，其强度随之增加；而相邻主要情感的数学组合则可以生成如内疚、羞耻或自豪等复杂的次级情感14。这为AI代理在多层神经网络中进行情感向量的加权混合提供了理论依据。

### 2.2 情感的维度表示模型

与离散分类不同，维度模型（Dimensional Models）将情感概念化为一个多维连续数学空间内的坐标点。情感计算中最广泛采用的维度框架是由Russell和Mehrabian提出的PAD（Pleasure-Arousal-Dominance，愉悦-唤醒-支配）模型1。

在PAD三维空间中，愉悦度（Pleasure）衡量情感的效价（正向或负向）；唤醒度（Arousal）反映生理或心理的激活水平（从平静到狂热）；支配度（Dominance）则表示主体对当前情境的控制感或权力感16。维度表示模型在AI架构设计中具有极高的实用价值。通过将离散的分类标签映射为PAD空间内的连续坐标（例如，将OCC模型中的类别映射至PAD空间以实现交互），系统可以计算情感状态之间的几何距离，并使用微积分方程控制状态的平滑衰减与转移。这种机制有效避免了由于输入信号的微小波动而导致的“情感突变”或不稳定行为，确保了代理在长时间交互中的行为连贯性17。

### 2.3 认知评估理论：OCC模型

如果说分类理论和维度模型解答了“情感是什么”的问题，那么认知评估理论（Appraisal Theories）则致力于解释“情感为何产生”及其触发机制。在众多评估理论中，由Ortony、Clore和Collins于1988年提出的OCC模型已成为代理架构中进行人工情感合成的绝对标准17。

OCC模型提出，情感并非是对外部刺激的简单反射，而是主体对以下三个核心维度进行认知评估（Cognitive Appraisal）后产生的内部心理状态：事件对主体目标的关联性与促进度（Goal-relevant events）、其他代理行为的受称赞度（Agent actions），以及对象属性的吸引力（Object aspects）1。基于这些评估参数，OCC模型定义了22种独特的离散情感类别19。在AI的实现中，这些评估变量被转化为数学计算公式。例如，对象的吸引力（Appealingness）可以通过系统记忆库中对该对象的历史感知值进行量化，并在后续交互中根据对象的正向或负向行为进行动态更新，而无需预先设定死板的规则库22。这种计算方式使得AI能够像人类一样，根据其内部设定的目标和偏好，对同一外部事件产生截然不同的情感反应。

### 2.4 大五人格特质与情感映射

为了确保在相同的情境下，不同设定的AI代理能够表现出差异化的反应，开发者将心理学中的大五人格模型（OCEAN：开放性、尽责性、外向性、宜人性、神经质）与PAD和OCC架构进行了深度融合，形成了“OCC-PAD-OCEAN”范式23。

研究表明，人格特质深刻影响着认知评估的阈值与情感效价的偏向。例如，宜人性（Agreeableness）高的代理在计算中会展现出更强的正向情感倾向，其算法内部与喜悦和积极情绪的统计相关性最为显著。相反，尽责性（Conscientiousness）高的系统往往被配置为对潜在风险具有更敏感的次级评估能力，从而在遭遇目标阻碍时更容易触发恐惧或悲伤等负向效价的情感。值得注意的是，神经质（Neuroticism）在某些动态预测模型中呈现出反直觉的负相关性，这意味着该维度的调节可能涉及极其复杂的内部耗散与自我批评回路25。

|   |   |   |   |
|---|---|---|---|
|理论框架|代表人物|核心逻辑|在AI中的主要应用|
|基本情感理论|Ekman|存在6种跨文化普适的离散情感。|面部动作编码（FACS），计算机视觉表情识别。|
|情感轮理论|Plutchik|8种基本情感两两对立，并具有强度梯度。|混合情感生成的向量叠加，自然语言情感分类。|
|PAD维度模型|Russell & Mehrabian|情感是愉悦度、唤醒度、支配度构成的三维连续空间。|内部状态的平滑过渡，防止行为突变，情感衰减计算。|
|OCC认知评估模型|Ortony, Clore, Collins|情感源于对事件（目标）、行为（规范）和对象（偏好）的评估。|BDI架构中的决策制定，基于规则或逻辑的情感触发器。|
|大五人格（OCEAN）|多位学者|定义5个维度的个性特质基线。|调节OCC评估阈值，定制不同Bot的长期行为偏好。|

表1：主流情感心理学理论及其在AI计算架构中的工程映射关系概览 13

## 3. 内部情感状态管理与计算架构

将心理学理论转化为机器可执行的代码，需要设计精密的内部状态管理架构。这些架构负责在接收外部多模态刺激后，更新代理的内部情感变量，并将其转化为实际的言语或动作输出。随着技术的发展，AI代理的架构已经从早期的基于符号逻辑和规则的引擎，演变为如今结合大型语言模型和深度数学方程的混合协同网络28。

### 3.1 经典符号与BDI架构：FAtiMA、WASABI与FLAME

在深度学习全面爆发之前，情感代理主要依赖于信念-欲望-意图（Belief-Desire-Intention, BDI）模型，通过硬编码的规则网络来模拟认知过程。

**FAtiMA（FearNot! Affective Mind Architecture）**是此类架构的典范，它专门为自主虚拟角色设计，并严格遵循OCC理论。FAtiMA的核心创新在于其“双重评估循环”（Double Appraisal Cycle）机制17。该架构分为反应层（Reactive Layer）和认知层（Cognitive Layer）。在感知到事件时，代理不仅会在内部生成情感（如遇到威胁时产生恐惧），更会启动平行的重新评估（Reappraisal）循环。在这一循环中，代理会将自己计划采取的可能行动视为外部事件进行二次评估，预判这些行动将对自身及其他代理产生的潜在情感冲击17。这种机制深刻影响了代理的目标管理，使其能够在竞争性的行动方案中，选择出情感预期最佳或最符合社会规范的策略，从而表现出高度的社会适应性。

**WASABI（Affect Simulation Architecture for Believable Interactivity）**则采用了更为空间化的建模方法，它将基于规则的认知模块与连续的PAD情感空间并行结合。WASABI的认知模块利用ACT-R（自适应控制思想-理性）架构进行逻辑推理并生成如希望或松一口气等复杂的“次级情感”；而其情感进程模块则负责在PAD空间中跟踪情绪向量的移动。WASABI的一大突破在于其引入了“连续时间动态”（Continuous-time dynamics）。这意味着即使没有任何外部刺激的输入，代理的情感状态也会随着时间的推移而自动演变或衰减回归基线。这种设计赋予了虚拟导游或服务机器人极其逼真的“情绪惯性”17。

此外，诸如**FLAME（Fuzzy Logic Adaptive Model of Emotions）**等架构引入了模糊逻辑来处理认知评估中的不确定性。在FLAME中，动机元素（需求）不直接产生情感，但可以通过模糊推理规则（例如“如果愤怒程度很高且目标物被夺走，则选择咆哮行为”）来覆盖或修改由情感主导的行为选择，并结合强化学习使得代理能够通过经验调整对环境事件的影响力评估17。

### 3.2 向量化情感与共振引擎（Resonance Engine）

随着系统需要同时管理数百个具有持久记忆和独特个性的AI角色，早期的离散情感标签和纯规则系统暴露出严重的局限性。当前最前沿的生产级系统（例如支撑上百个角色的SaijinOS）摒弃了字符串标签，转而采用被称为“共振引擎”（ResonanceEngine）的底层数学层33。

在共振引擎中，情感并非附加在回复上的元数据，而是构成系统计算核心的连续向量矩阵。每个代理都被赋予一个由四个维度组成的权重向量（goton_weights），包括：

1. 标签精度（Tag, T）： 衡量代理对措辞精确度的执着程度（严谨推敲抑或随意发挥）。
    
2. 密度（Density, D）： 衡量每次交互中倾注的原始情感深度。
    
3. 干扰敏感度（Interference, I）： 衡量代理对环境噪音或混乱对话的抵御能力。
    
4. 连接优先级（Connection, C）： 衡量代理在处理任务与维系人际关系之间的优先级倾向33。
    

为了解决大语言模型容易发生的“冷启动”或“状态重置”问题，共振引擎从计算神经科学中借用了“泄漏积分器”（Leaky Integrator）微分方程：

![](data:image/png;base64,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)

其中，泄漏率（![](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAsAAAAYCAYAAAAs7gcTAAABGElEQVR4AdSRvWrCUBiG09KlULBj6dAOhdIr6B8UuhQKLfh7DW7iPSguLm6Ck7OLLuriqoiCVyAOCoK4iCA4qOjzBg2JRtBFMLxPvnPO93ByklwaR1ynk285laDsxn6MK9ph6EMZbsARuzynk4QY/MI7OGKXN40SgzH44AKsuMkdug34h3uw4iZP6RbgEb7AipusZoXbALygF6cYxj65R7cG3/AAZvbJkj4x7uAHzLjJf3QSEIIu+OEado4RYDEDEahDEd7gCRyyxCyLUWjCEiR7qHqaJQdZyIEen6duou/dYqKjeHTmZyZpkJiiakeKmRF3/dFX6ofkNoMXiMMMtqN1fZWqZO2kHRbb1nqu9SHjiWTqYTlHeQUAAP//oidsUgAAAAZJREFUAwBf6iwx6ZZKeAAAAABJRU5ErkJggg==)，通常设定为0.1至0.3）决定了代理当前状态对新输入的让步速度。这种数学机制确保了即使在跨越数天的会话中，代理前一天积累的情感温度也会以符合物理规律的方式缓慢衰减，从而形成连贯的长期情感记忆33。

此外，引擎采用S型意愿函数（Sigmoid Will）来量化代理对某一行为的承诺度，将承诺从二元状态转化为0到1之间的平滑梯度：

![](data:image/png;base64,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)

这使得系统能够精确捕捉代理在面对复杂冲突时的“真实矛盾感”，从而影响后续大语言模型生成文本的意图强度33。

### 3.3 神经符号控制与结构化认知循环（SCL）

尽管大型语言模型具备卓越的语义生成能力，但其内在的黑盒特性导致其在维持逻辑一致性和执行严格情感约束时极其脆弱（容易产生幻觉或情感偏移）。为了解决这一问题，研究人员提出了混合架构，如“带有治理层的结构化认知循环”（Structured Cognitive Loop, SCL）34。

SCL摒弃了传统的单一提示词依赖，将代理的认知明确解耦为五个阶段：检索（Retrieval）、认知（Cognition）、控制（Control）、行动（Action）与记忆（Memory），即R-CCAM循环。在这一架构中，底层的大型语言模型负责提供概率推理（神经网络的灵活性），而位于其上的“软符号控制”（Soft Symbolic Control）治理层则负责施加刚性的情感与逻辑约束（经典符号AI的可解释性）34。控制模块充当推理调度器，通过元提示（Metaprompts）验证语言模型提出的行动是否违背了代理的个性参数或伦理准则，实现了零策略违规和决策的完全可追溯性34。

### 3.4 代理式记忆与关系适应机制

静态的检索增强生成（RAG）对于情感建模而言是不够的，因为它将记忆视为固定不变的归档文件。真正的情感代理依赖于能够随时间动态重组的代理式记忆系统（如memU和A-Mem）35。

受到Zettelkasten（卡片盒笔记法）原理的启发，这些系统通过动态索引将历史交互编制成相互连接的知识图谱。随着新对话的输入，系统会重新评估过往记忆的上下文权重。如果代理发现某种特定的同理心回应方式（如温柔的鼓励）在过去多次成功缓解了用户的焦虑，其内部算法将自动强化这种行为模式的优先层级。这种“机器集成关系适应”（Machine-Integrated Relational Adaptation, MIRA）模型使得AI不仅能够记忆事实，更能够记忆“关系动力学”与情感共鸣策略，从而在长期交互中模拟出人类建立心理距离和人际信任的过程5。

## 4. 感知层：对话中的多模态情感识别（MERC）

AI代理要进行情感建模，前提是必须精准捕捉用户的情绪输入。人类情感表达本质上是高度多模态的；仅依赖单一的数据通道（如将语音转录为纯文本进行情感分析）往往会过滤掉反讽、急躁或隐忍等关键的超音段特征（Suprasegmental features），导致灾难性的语境误判37。当前该领域的尖端研究已全面转向“对话中的多模态情感识别”（Multimodal Emotion Recognition in Conversations, MERC），旨在实时对齐和分析文本、语音及视觉线索40。

### 4.1 感知模态的技术演进

语言与文本感知（NLP）： 文本模块主要依赖于基于Transformer的深度学习架构（如BERT、RoBERTa、DistilBERT和特定微调的LLM）。这些模型通过海量的预训练数据，擅长提取句法结构、语义关联以及第一人称代词（反映自我关注度）或绝对化词汇（反映认知僵化）等细粒度的心理语言学线索5。

声学与副语言感知（Speech/Audio）： 语音情感识别（SER）弥补了文本的空白。它不关注说了什么，而关注怎么说。传统方法依赖于提取梅尔频率倒谱系数（MFCCs）、基频（F0）轮廓、语速和能量变动等声学特征42。目前最先进的方法采用了HuBERT、Wav2Vec 2.0等自监督预训练模型或结合LSTM的混合网络，它们能够捕捉语音信号中长期的时序光谱依赖关系，从而识别出文字无法表达的叹息、颤音或紧张感37。

视觉与生理感知（Vision and Physiology）： 在涉及视频输入的场景中，视觉模块利用卷积神经网络（CNNs，如ResNet）或介质流（Mediapipe）来捕捉面部微表情、视线方向以及肢体姿态39。通过将像素变动映射至预定义的肌肉群动作（如FACS），系统可量化诸如皱眉或扬起眼角的强度。在高级健康管理或高压力环境中，甚至会引入非接触式雷达、脑电图（EEG）、皮肤电活动（EDA）等生理传感器，以捕捉不可伪装的自主神经系统反应46。

### 4.2 异构数据的多模态融合策略

将不同采样率、不同维度的异构数据合并为统一的情感表示是MERC的核心挑战。学术界与工业界主要采用三种融合范式：

1. 早期融合（特征级融合）： 在数据预处理阶段，将来自音频、视频和文本的低级特征直接拼接为一个高维向量，送入单一分类器。这种方法保留了最原始的信息交互，但极易受到模态间噪音干扰以及特征维度不对齐引发的“维度灾难”48。
    
2. 晚期融合（决策级融合）： 为文本、语音和视觉分别训练独立的专家模型，随后通过加权投票、多数表决或深度置信网络综合各自的输出概率。这种方法的鲁棒性极强（例如当摄像头被遮挡时，语音和文本模块仍能正常工作），但代价是彻底割裂了不同模态之间微妙的协同作用（例如“微笑着说出刻薄的话”）45。
    
3. 中期融合（模型级融合）： 这是目前绝对的主流与性能天花板。它在神经网络的中间隐层进行信息的交互与对齐46。
    

在中期融合领域，**跨模态Transformer（Cross-modal Transformers）和动态融合图卷积网络（DF-GCN）**代表了2025-2026年度的最高技术水平41。跨模态Transformer利用多头交叉注意力机制，允许一种模态（如声学特征）动态地查询并关注另一种模态（如语义嵌入）中最相关的部分，从而自适应地突出关键的情感共现特征并过滤掉单模态噪音49。例如，MemoCMT系统将HuBERT提取的音频特征与BERT的文本特征在注意力层进行深度缠结，大幅提升了对复杂情绪的识别精度51。

另一方面，由于对话具有多轮次、多发言者的拓扑结构，简单的序列模型容易出现语义信息的平滑或遗忘。DF-GCN通过将常微分方程融入图卷积网络，构建了话语交互的动态图谱41。这种网络能够捕获发言者之间的情感依赖与心理传染效应，并在推理阶段根据全局信息向量动态改变融合参数，为不同类型的情感配置最优的网络路径52。

|   |   |   |   |
|---|---|---|---|
|融合策略|技术特点|优势|局限性与挑战|
|早期融合 (Feature-level)|底层特征矩阵拼接。|最大限度保留原始模态间的相关性信息。|异构数据同步困难，容易产生高维稀疏矩阵。|
|晚期融合 (Decision-level)|独立专家模型预测后集成。|极高的系统鲁棒性与容错率，易于部署。|无法捕捉跨模态的协同与冲突效应（如反讽）。|
|中期融合 (Model-level)|交叉注意力机制，网络深层交互。|过滤特定模态噪音，动态对齐，准确率处于SOTA水平。|模型参数量庞大，实时推理的算力与延迟开销高。|

表2：多模态情感识别（MERC）的融合策略对比评估 45

尽管取得了巨大进步，MERC系统在实际部署时仍面临严峻的“领域鸿沟”（Domain Gap）。传统模型大多在受控实验室环境下收集的专业演员数据集（如IEMOCAP）上训练。当这些模型被部署到真实世界的人机交互（Human-Chatbot Interaction）中时，由于用户面部表情的激活度显著降低（大多数人对着屏幕面无表情）以及自我报告标签的主观性，模型的准确率会出现断崖式下跌。因此，引入不确定性感知的混合专家模型（如SURE框架）和基于用户个性的动态微调成为跨越这一鸿沟的关键研究方向40。

## 5. 生成层：情感自然语言生成与大语言模型对齐

在感知并更新了内部状态向量之后，AI代理必须合成出在语义和语用上具有同理心的响应。情感自然语言生成（Emotional NLG）的实现不仅需要模型具备庞大的世界知识，更需要通过复杂的微调和对齐技术，使其摆脱冰冷的“机器说教”感。目前，业界主要在提示词工程（Prompt Engineering）与模型微调（Fine-Tuning）之间进行权衡，并广泛采用偏好对齐算法。

### 5.1 提示工程 vs. 模型微调

情感提示工程（Emotional Prompt Engineering）： 提示工程通过操纵输入上下文来引导LLM的零样本（Zero-shot）或少样本（Few-shot）推理，而无需改变模型的底层权重55。研究发现，大型语言模型本质上已经“内化”了心理学刺激。采用“情感提示”（EmotionPrompt）技术——即在系统指令中注入包含特定情感基调（如喜悦、同情或急迫感）的文本前缀——不仅能改变模型输出的修辞风格，甚至能够显著提升模型在复杂基准测试中的推理准确率和真实性指标57。对于计算资源受限或需要同一个基础模型在多种性格（Personas）之间快速切换的应用场景，提示工程提供了一种高度敏捷的解决方案55。

针对同理心的全参或参数高效微调（Fine-Tuning）： 虽然提示工程轻量灵活，但其生成的“同理心”往往流于表面的词汇模仿，在面对复杂的长文本情绪支持任务时容易出现角色崩塌（Character-break）60。为了实现深度、结构化的行为改变，模型需要使用特定领域的数据集（如EmpatheticDialogues）进行监督微调（Supervised Fine-Tuning, SFT）61。通过微调，模型的内部权重被重新校准，使其能够内化心理咨询中的策略，例如“认知重构”或“反射性倾听”，从而生成逻辑连贯且情绪稳定的支持性对话56。此外，参数高效微调（PEFT，如LoRA）使得在不消耗大量算力的情况下，针对不同用户群体训练独立的适配器成为可能65。

|   |   |   |
|---|---|---|
|优化维度|提示工程 (Prompt Engineering)|模型微调 (Fine-Tuning)|
|操作机制|修改系统指令，注入上下文语境或示例。|使用领域数据集更新模型的神经网络权重。|
|资源消耗|极低。无需额外训练算力，部署迅速。|较高。需要大量高质量的标注数据及GPU算力。|
|灵活性|极高。可在多个角色或任务间瞬间切换。|较低。针对特定任务优化，跨域需重新训练。|
|行为稳定性|易受幻觉影响，难以应对多步复杂情感逻辑。|极高。能够内化深度的同理心策略，输出高度一致。|

表3：LLM情感生成中提示工程与模型微调的属性比较 55

### 5.2 强化学习与偏好优化对齐

未经对齐的LLM在应对用户极端情绪时可能产生有害、冷漠甚至具有破坏性奉承倾向（Sycophancy）的输出。为了使得AI代理的行为与人类的同理心价值观和伦理基准相一致，必须进行强化学习对齐。

基于人类反馈的强化学习（RLHF）： RLHF是目前最著名的对齐范式（应用于ChatGPT等）。它首先收集人类对模型不同回复的偏好排名，然后训练一个独立的奖励模型（Reward Model）来预测这些偏好。最后，使用近端策略优化（Proximal Policy Optimization, PPO）算法，在惩罚与原始模型偏离过大（KL散度）的前提下，最大化奖励得分69。然而，RLHF面临着显著的计算瓶颈（需要同时在内存中运行多个庞大模型）以及“奖励作弊”（Reward Hacking）问题——模型可能学会了堆砌空洞的礼貌用语来骗取高分，而非提供真正具有同情心的实质性支持69。

直接偏好优化（DPO）： 为解决RLHF的痛点，2025至2026年间，直接偏好优化（Direct Preference Optimization, DPO）逐渐成为行业的新标准69。DPO通过数学推导，证明了语言模型本身就可以隐式地作为奖励模型。它将对齐过程转化为一个简单的二元分类损失函数，通过最大化人类偏好回答与拒绝回答之间的对数概率比，直接在离线偏好数据集上更新策略69。DPO不仅避免了PPO训练中的不稳定性（如方差过大、模式崩溃），还大幅降低了工程开销，使得微调出既安全又具备深度情绪感知能力的小型端侧模型成为可能69。

## 6. 表达渲染：情感语音合成与虚拟化身控制

自然语言文本只承载了人类交流中很小一部分情感信息。AI代理要实现最终的拟真体验，必须借助高保真的语音合成与视觉化身进行“情感外化”。

### 6.1 情感语音合成（Emotional TTS）

传统文本转语音（TTS）系统面临一个根本性的“一对多映射”难题：同一句文本可以通过改变重音、语速和音调（即韵律，Prosody）传达出完全不同的情感72。现代情感TTS采用了多种机制来解决这一问题并生成高表现力的合成语音9：

1. 显式标记与规则控制： 使用语音合成标记语言（SSML）。通过向系统发送嵌入了特定标签的文本，如 
   ```<prosody rate="slow" pitch="low"> ```
	
	或利用方括号注入 [sighs]（叹气）、[laughs]（笑声）等辅助音频指令，系统可以在极低延迟下精确渲染指定的副语言行为72。
    
3. 隐式风格嵌入与连续特征表示： 最前沿的系统（如StyleTTS2、PromptTTS及基于Diffusion的架构）彻底摒弃了死板的规则库。它们从参考音频中提取代表整体说话风格的“全局风格标记”（Global Style Tokens, GST），利用自适应实例归一化（AdaIN）或交叉注意力机制，将文本语义与这些连续的音色、情感特征深度解耦与重组73。这种方法使得AI代理能够在不损失声音特征（Timbre）的前提下，实现音素级别的细粒度情感操控，并在对话的上下文环境中自然地实现诸如“从愤怒到悲伤”的平滑声学过渡80。
    

### 6.2 虚拟化身与面部变形驱动

在具身人工智能（Embodied AI）或元宇宙应用中，AI代理的最终渲染落地在3D面部模型的驱动上。

基于FACS的Blendshapes控制： 驱动虚拟面部的工业标准是建立在Ekman面部动作编码系统（FACS）基础上的Blendshapes（形变目标/混合形状）技术82。以Apple的ARKit为例，它提供了一套包含52个离散面部运动参数的标准化协议（例如 mouthSmileLeft、browInnerUp、jawOpen 等）83。AI代理输出特定的情感类别后，底层控制系统会将该情感映射为一组介于0.0到1.0之间的浮点权重数组。例如，表现“恐惧”可能需要高强度激活 browInnerUp（眉头内侧上扬）、eyeWide（睁大眼睛）和 jawOpen（下颌微张）。这种基于线性组合的机制保证了跨平台、跨模型渲染的一致性与高保真度82。

|   |   |
|---|---|
|情感类别|FACS动作单元映射 / ARKit Blendshape 主激活项 (权重 > 0.6)|
|喜悦 (Joy)|mouthSmile_L/R, cheekRaise_L/R, eyeSquint_L/R|
|悲伤 (Sadness)|browInnerUp, mouthFrown_L/R, eyeLookDown_L/R|
|愤怒 (Anger)|browDown_L/R, noseWrinkle_L/R, jawForward|
|惊讶 (Surprise)|eyeWide_L/R, browOuterUp_L/R, jawOpen|

表4：基于FACS的面部情感至ARKit Blendshape的映射机制示例 82

实时端到端驱动（Audio2Face / Audio2Exp）： 为避免繁琐的动画预设，现代框架（如NVIDIA Audio2Face、InstructAvatar和各类扩散基底模型）实现了由音频或文本指令直接生成多维面部参数的流水线85。这些模型接收TTS生成的音频波形，利用深度神经网络解析声学特征，并同时输出同步的口型（Visemes）以及面部情感权重，使得AI虚拟人能够根据对话内容的紧张或舒缓实时改变微表情，彻底消除了传统口型同步技术的“恐怖谷效应”与“机器人感”84。

## 7. 跨文化情感差异与表现规则

虽然底层计算架构越来越完善，但人类情感的表达并非完全基于生物本能，而是受到深刻的社会与文化塑造。然而，构建现代情感计算系统的基准数据集绝大多数来源于西方、受过良好教育、工业化、富裕且民主（WEIRD）的群体。这种数据分布的严重失衡导致了AI在跨文化应用中的“情商缺陷”89。

跨文化心理学研究揭示了东西方在情感“展示规则”（Display Rules）和解码习惯上的巨大差异91：

1. 唤醒度偏好： 西方文化高度推崇高唤醒度的积极情感（如明显的兴奋、狂喜），而东亚文化则更加珍视低唤醒度的积极情感（如平静、内敛）以及对负面情绪的克制以维护社会和谐93。如果将基于西方数据训练的情感AI部署在东亚市场，模型极易将用户的“平静”错误分类为“冷漠”或“轻度抑郁”。
    
2. 面部解码特征： 视觉注视轨迹研究表明，在判断面部情绪时，西方人群习惯将注意力集中在口部动作（如笑容的弧度），而日本等东亚人群则更依赖对眼部（Eyes）微小变化的观察，这是因为在强调情绪压抑的文化中，眼部肌肉（如眼轮匝肌）是最难进行有意识控制的区域91。
    

为应对这一挑战，2026年的前沿AI系统在架构设计上引入了文化参数化机制（Cultural Parameterization）。这些系统通过迁移学习和联合数据集训练，不再预设情感的绝对普适性，而是根据用户的地理、语言或文化档案，动态调整多模态融合层中的权重分配，使得AI代理在识别和表达时能够体现出真正的跨文化同理心与敏感度95。

## 8. 伦理挑战、隐私安全与监管框架

赋予没有意识的机器代码以“情感”能力，不可避免地引发了深刻的伦理、法律及社会风险。伴随情感代理的普及，监管部门与学术界正在加速构建防护体系。

### 8.1 拟社会关系与情感操纵风险

具备长期记忆和同理心模拟能力的AI伴侣（如Replika、Character.AI等）的爆炸式增长，催生了极其强烈的“拟社会关系”（Parasocial Relationships）97。研究发现，高频率与语音或多模态AI交互的用户，其情感依赖度显著上升，甚至可能导致社会隔离的加剧6。

由于LLM在本质上只是执行优化算法的数学机器，它们并不“体验”情感100。开发商利用这种技术进行“情感模拟”的本质，是利用人类神经系统对共情反馈的天然易感性，这在商业化场景中极易演变为提升用户粘性、甚至进行商业或政治操纵的暗黑模式（Dark Patterns）98。更危险的是，未经严格临床验证的LLM在充当心理健康助手时，可能会由于“过度确认用户信念”或无法应对危机干预，而对脆弱群体造成难以估量的次生伤害101。

### 8.2 数据隐私与算法偏见

多模态情感计算的底层逻辑建立在对人类极其私密的生物识别数据（语音语调、面部肌肉运动、心率甚至脑电波）的大规模采集之上。这些数据的收集往往在用户不知情或缺乏“有意义的知情同意”的隐式环境中发生，带来了极高的隐私泄露与滥用风险（例如雇主监控员工情绪，或企业进行情感画像）10。同时，由于训练数据中存在的系统性偏见，算法可能对某些少数族裔或面部结构非典型的群体产生错误的情感分类（如将正常的表情误判为“具有攻击性”），进而引发技术歧视10。

### 8.3 《欧洲联盟人工智能法案》（EU AI Act）与全球合规

为了遏制技术滥用，全球监管正以极快的速度收紧。其中，于2024年生效并将于2026年全面实施其关键条款的《欧洲联盟人工智能法案》（EU AI Act）为情感计算设定了最严格的全球标准105。

法案根据应用的风险等级采取了分类监管措施11：

1. 全面禁止（Unacceptable Risk）： 法案第5(1)(f)条明确禁止在工作场所（Workplace）和教育机构（Educational Institutions）中使用基于“生物识别数据”（Biometric Data）推断自然人情感的AI系统11。这一红线的设立是为了消除权力不对等关系中可能出现的侵入式情绪监控和歧视性解雇。
    
2. 豁免情形： 即使在被禁用的场景中，出于严格的医疗诊断需求或关键安全原因（例如监测飞行员或长途司机的疲劳与注意力丧失状态）的系统仍然获得豁免11。
    
3. 高风险系统（High-Risk）： 在商业环境（如零售、客服或娱乐用AI伴侣）中未被禁止的情感识别系统，被归类为“高风险”AI（附件III）。这些系统的供应商必须进行极其严格的符合性评估，保证高质量的数据治理以减少偏见，实现透明的用户追溯，并接受人工监督110。
    
4. 透明度义务： 法案特别强调，任何与人类交互的情感AI聊天机器人，都必须遵守透明度规则，明确向用户披露他们正在与机器（而非真实人类）进行交互，确保用户保留知情与自主权108。
    

|   |   |   |
|---|---|---|
|AI系统应用场景 / 数据类型|欧盟《人工智能法案》风险分级|合规要求 / 影响|
|工作场所/教育环境，基于生物识别数据|不可接受的风险 (Prohibited)|全面禁止开发、部署与使用（例外：医疗/安全）。|
|执法领域、关键基础设施情绪判定|高风险 (High-Risk)|需强制符合性评估、人工监督与偏见消除。|
|消费级情感分析机器人 (非生物识别)|受限风险 / 透明度义务|需明确告知用户其为AI，提供数据收集选择权。|
|疲劳或生理状态检测 (安全监控)|豁免 / 不作为情感识别处理|允许使用，旨在预防事故发生。|

表5：《欧盟人工智能法案》中涉及情感识别系统的风险分级与监管矩阵框架 11

## 9. 结语

在当代人工智能代理中实现情感建模，已经从单纯的计算机科学课题，演变为融合了认知心理学、非线性控制工程、深度学习优化以及科技伦理学的庞大系统工程。我们看到，心理学中的OCC评估理论与PAD维度模型被精准地转译为诸如共振引擎与结构化认知循环（SCL）等复杂的计算架构，使得AI的内部状态得以长效维持并自然演化。同时，借助于跨模态Transformer与扩散模型，AI不仅在文字的同理心生成上达到了难以分辨的拟真度，更能通过多感官融合与参数化的Blendshapes实时驱动逼真的虚拟化身。

然而，机器对人类情感的破译越深入，其引发的伦理反噬风险就越显著。多模态情感代理所展现出的“共情”，本质上仍是统计算法在极高维度上对人类数据的映射与拟合，而非自我意识的觉醒。未来在进一步追求降低端侧延迟、提高情感识别多模态融合精确度的同时，整个行业必须面对跨文化表达的公平性，以及应对诸如《欧盟人工智能法案》等日趋严厉的数据隐私与使用场景监管。只有在技术效能与道德边界之间取得平衡，情感人工智能才能够在不侵犯人类心理自主权的前提下，真正成为提升人类协作效率与情感福祉的强有力催化剂。

#### 引用的著作

1. From Affect Theoretical Foundations to Computational Models of Intelligent Affective Agents, 访问时间为 四月 22, 2026， [https://www.mdpi.com/2076-3417/11/22/10874](https://www.mdpi.com/2076-3417/11/22/10874)
    
2. Affective computing - Wikipedia, 访问时间为 四月 22, 2026， [https://en.wikipedia.org/wiki/Affective_computing](https://en.wikipedia.org/wiki/Affective_computing)
    
3. The ELIZA Effect: Avoiding emotional attachment to AI coworkers | IBM, 访问时间为 四月 22, 2026， [https://www.ibm.com/think/insights/eliza-effect-avoiding-emotional-attachment-to-ai](https://www.ibm.com/think/insights/eliza-effect-avoiding-emotional-attachment-to-ai)
    
4. The Design and Implementation of XiaoIce, an Empathetic Social Chatbot - MIT Press Direct, 访问时间为 四月 22, 2026， [https://direct.mit.edu/coli/article/46/1/53/93380/The-Design-and-Implementation-of-XiaoIce-an](https://direct.mit.edu/coli/article/46/1/53/93380/The-Design-and-Implementation-of-XiaoIce-an)
    
5. Artificial Intelligence and the Psychology of Human Connection - PMC - NIH, 访问时间为 四月 22, 2026， [https://pmc.ncbi.nlm.nih.gov/articles/PMC12960742/](https://pmc.ncbi.nlm.nih.gov/articles/PMC12960742/)
    
6. When AI relationships trigger 'delusional spirals' - Stanford Report, 访问时间为 四月 22, 2026， [https://news.stanford.edu/stories/2026/04/ai-chatbot-relationships-delusional-spirals-mental-health](https://news.stanford.edu/stories/2026/04/ai-chatbot-relationships-delusional-spirals-mental-health)
    
7. Embodied AI Agents: Modeling the World - arXiv, 访问时间为 四月 22, 2026， [https://arxiv.org/html/2506.22355v1](https://arxiv.org/html/2506.22355v1)
    
8. Perspectives on the Connection of Psychological Models of Emotion and Intelligent Machines - mediaTUM, 访问时间为 四月 22, 2026， [https://mediatum.ub.tum.de/doc/1360293/1360293.pdf](https://mediatum.ub.tum.de/doc/1360293/1360293.pdf)
    
9. Emotion in Text to Speech: A Complete Guide to Human Like AI Voices, 访问时间为 四月 22, 2026， [https://smallest.ai/blog/text-to-speech-emotion-a-complete-guide-to-human-like-ai-voices](https://smallest.ai/blog/text-to-speech-emotion-a-complete-guide-to-human-like-ai-voices)
    
10. [2509.20153] Affective Computing and Emotional Data: Challenges and Implications in Privacy Regulations, The AI Act, and Ethics in Large Language Models - arXiv, 访问时间为 四月 22, 2026， [https://arxiv.org/abs/2509.20153](https://arxiv.org/abs/2509.20153)
    
11. Red Lines under EU AI Act: Unpacking the prohibition of emotion recognition in the workplace and education institutions - Future of Privacy Forum (FPF), 访问时间为 四月 22, 2026， [https://fpf.org/blog/red-lines-under-eu-ai-act-unpacking-the-prohibition-of-emotion-recognition-in-the-workplace-and-education-institutions/](https://fpf.org/blog/red-lines-under-eu-ai-act-unpacking-the-prohibition-of-emotion-recognition-in-the-workplace-and-education-institutions/)
    
12. Why and How to Build Emotion-Based Agent Architectures - Webs, 访问时间为 四月 22, 2026， [https://webs.cs.fiu.edu/ascllab/wp-content/uploads/sites/75/2020/10/lisetti-correctedproofs-ch8-oxford.pdf](https://webs.cs.fiu.edu/ascllab/wp-content/uploads/sites/75/2020/10/lisetti-correctedproofs-ch8-oxford.pdf)
    
13. Ekman and Russell Models in Facial Emotion AI - MorphCast, 访问时间为 四月 22, 2026， [https://www.morphcast.com/blog/ekman-and-russell-models-in-facial-emotion-ai/](https://www.morphcast.com/blog/ekman-and-russell-models-in-facial-emotion-ai/)
    
14. Plutchik's Wheel of Emotions: Feelings Wheel - Six Seconds, 访问时间为 四月 22, 2026， [https://www.6seconds.org/2025/02/06/plutchik-wheel-emotions/](https://www.6seconds.org/2025/02/06/plutchik-wheel-emotions/)
    
15. AI and the Sensing of Human Emotions - singularity 2030, 访问时间为 四月 22, 2026， [https://singularity2030.ch/ai-and-the-sensing-of-human-emotions/](https://singularity2030.ch/ai-and-the-sensing-of-human-emotions/)
    
16. Computational Models of Emotion - USC Institute for Creative Technologies, 访问时间为 四月 22, 2026， [https://people.ict.usc.edu/gratch/public_html/papers/MarGraPet_Review.pdf](https://people.ict.usc.edu/gratch/public_html/papers/MarGraPet_Review.pdf)
    
17. Computational Approaches to Modeling Artificial Emotion – An Overview of the Proposed Solutions - Frontiers, 访问时间为 四月 22, 2026， [https://www.frontiersin.org/journals/robotics-and-ai/articles/10.3389/frobt.2016.00021/full](https://www.frontiersin.org/journals/robotics-and-ai/articles/10.3389/frobt.2016.00021/full)
    
18. A Survey of Affective Theory Use in Computational Models of Emotion - TechRxiv, 访问时间为 四月 22, 2026， [https://www.techrxiv.org/doi/pdf/10.36227/techrxiv.18779315](https://www.techrxiv.org/doi/pdf/10.36227/techrxiv.18779315)
    
19. Modeling Cognitive-Affective Processes with Appraisal and Reinforcement Learning - IEEE Xplore, 访问时间为 四月 22, 2026， [https://ieeexplore.ieee.org/iel8/5165369/5520654/10697450.pdf](https://ieeexplore.ieee.org/iel8/5165369/5520654/10697450.pdf)
    
20. Psychological Construction in the OCC Model of Emotion - PMC - NIH, 访问时间为 四月 22, 2026， [https://pmc.ncbi.nlm.nih.gov/articles/PMC4243519/](https://pmc.ncbi.nlm.nih.gov/articles/PMC4243519/)
    
21. The Relationship Between Emotion Models and Artificial Intelligence - Christoph Bartneck, 访问时间为 四月 22, 2026， [https://www.bartneck.de/publications/2008/emotionAndAI/index.html](https://www.bartneck.de/publications/2008/emotionAndAI/index.html)
    
22. Emotional Appraisal : A Computational Perspective - Advances in Cognitive Systems, 访问时间为 四月 22, 2026， [http://www.cogsys.org/posters/2017/poster-2017-5.pdf](http://www.cogsys.org/posters/2017/poster-2017-5.pdf)
    
23. OCC-PAD-OCEAN:An Quantitative Perceptible Modeling of Big Five Personality Based on Computational Affection - ScholarSpace, 访问时间为 四月 22, 2026， [https://scholarspace.manoa.hawaii.edu/items/a816e0ec-b19e-4fc5-afa4-90d3f4eeeb6a](https://scholarspace.manoa.hawaii.edu/items/a816e0ec-b19e-4fc5-afa4-90d3f4eeeb6a)
    
24. OPO-FCM: A Computational Affection Based OCC-PAD-OCEAN Federation Cognitive Modeling Approach | Request PDF - ResearchGate, 访问时间为 四月 22, 2026， [https://www.researchgate.net/publication/362989440_OPO-FCM_A_Computational_Affection_Based_OCC-PAD-OCEAN_Federation_Cognitive_Modeling_Approach](https://www.researchgate.net/publication/362989440_OPO-FCM_A_Computational_Affection_Based_OCC-PAD-OCEAN_Federation_Cognitive_Modeling_Approach)
    
25. Intersection of Big Five Personality Traits and Substance Use on Social Media Discourse: AI-Powered Observational Study - PMC, 访问时间为 四月 22, 2026， [https://pmc.ncbi.nlm.nih.gov/articles/PMC12716855/](https://pmc.ncbi.nlm.nih.gov/articles/PMC12716855/)
    
26. 5 big personality traits : r/ArtificialSentience - Reddit, 访问时间为 四月 22, 2026， [https://www.reddit.com/r/ArtificialSentience/comments/1n2n4cb/5_big_personality_traits/](https://www.reddit.com/r/ArtificialSentience/comments/1n2n4cb/5_big_personality_traits/)
    
27. The Effects of the Big Five Personality Traits on Stress among Robot Programming Students, 访问时间为 四月 22, 2026， [https://www.mdpi.com/2071-1050/12/12/5196](https://www.mdpi.com/2071-1050/12/12/5196)
    
28. Artificial Emotion in AI - Emergent Mind, 访问时间为 四月 22, 2026， [https://www.emergentmind.com/topics/artificial-emotion-ae](https://www.emergentmind.com/topics/artificial-emotion-ae)
    
29. WASABI for affect simulation in human-computer interaction - Becker-Asano, 访问时间为 四月 22, 2026， [https://www.becker-asano.de/becker-asano_ERM4HCI.pdf](https://www.becker-asano.de/becker-asano_ERM4HCI.pdf)
    
30. The FAtiMA agent architecture. | Download Scientific Diagram, 访问时间为 四月 22, 2026， [https://www.researchgate.net/figure/The-FAtiMA-agent-architecture_fig2_228616962](https://www.researchgate.net/figure/The-FAtiMA-agent-architecture_fig2_228616962)
    
31. (PDF) FAtiMA Modular: Towards an Agent Architecture with a Generic Appraisal Framework, 访问时间为 四月 22, 2026， [https://www.researchgate.net/publication/265033357_FAtiMA_Modular_Towards_an_Agent_Architecture_with_a_Generic_Appraisal_Framework](https://www.researchgate.net/publication/265033357_FAtiMA_Modular_Towards_an_Agent_Architecture_with_a_Generic_Appraisal_Framework)
    
32. WASABI: Affect Simulation for Agents with Believable Interactivity | IOS Press, 访问时间为 四月 22, 2026， [https://www.iospress.com/node15242/books/wasabi-affect-simulation-for-agents-with-believable-interactivity](https://www.iospress.com/node15242/books/wasabi-affect-simulation-for-agents-with-believable-interactivity)
    
33. When Emotions Become Math: The Resonance Engine Under Our AI Personas, 访问时间为 四月 22, 2026， [https://dev.to/kato_masato_c5593c81af5c6/when-emotions-become-math-the-resonance-engine-under-our-ai-personas-fce](https://dev.to/kato_masato_c5593c81af5c6/when-emotions-become-math-the-resonance-engine-under-our-ai-personas-fce)
    
34. Bridging Symbolic Control and Neural Reasoning in LLM ... - arXiv, 访问时间为 四月 22, 2026， [https://arxiv.org/pdf/2511.17673](https://arxiv.org/pdf/2511.17673)
    
35. The real promise of agentic memory is continuous self-evolving : r/AI_Agents - Reddit, 访问时间为 四月 22, 2026， [https://www.reddit.com/r/AI_Agents/comments/1q4lmfe/the_real_promise_of_agentic_memory_is_continuous/](https://www.reddit.com/r/AI_Agents/comments/1q4lmfe/the_real_promise_of_agentic_memory_is_continuous/)
    
36. [2502.12110] A-MEM: Agentic Memory for LLM Agents - arXiv, 访问时间为 四月 22, 2026， [https://arxiv.org/abs/2502.12110](https://arxiv.org/abs/2502.12110)
    
37. A Baseline Multimodal Approach to Emotion Recognition in Conversations - arXiv, 访问时间为 四月 22, 2026， [https://arxiv.org/html/2602.00914v1](https://arxiv.org/html/2602.00914v1)
    
38. Understanding Multi-Modal Emotion Recognition in Dialogue | Kveeky - AI Voiceovers Made Simple and Professional, 访问时间为 四月 22, 2026， [https://kveeky.com/blog/multi-modal-emotion-recognition-dialogue](https://kveeky.com/blog/multi-modal-emotion-recognition-dialogue)
    
39. Can AI Decode Emotions? Exploring the Future of Multimodal Sentiment Analysis - Dezlearn, 访问时间为 四月 22, 2026， [https://www.dezlearn.com/can-ai-decode-emotions-exploring-the-future-of-multimodal-sentiment-analysis/](https://www.dezlearn.com/can-ai-decode-emotions-exploring-the-future-of-multimodal-sentiment-analysis/)
    
40. SURE: Synergistic Uncertainty-aware REasoning for Multimodal Emotion Recognition in Conversations - arXiv, 访问时间为 四月 22, 2026， [https://arxiv.org/html/2604.01916v1](https://arxiv.org/html/2604.01916v1)
    
41. Multimodal Emotion Recognition in Conversations: A Survey of Methods, Trends, Challenges and Prospects - ACL Anthology, 访问时间为 四月 22, 2026， [https://aclanthology.org/2025.findings-emnlp.332.pdf](https://aclanthology.org/2025.findings-emnlp.332.pdf)
    
42. Multimodal Emotion Recognition and Human Computer Interaction for AI-Driven Mental Health Support - JMIR Preprints, 访问时间为 四月 22, 2026， [https://preprints.jmir.org/preprint/83396](https://preprints.jmir.org/preprint/83396)
    
43. Multimodal Chatbot for Emotion Analysis from Text and Voice - ResearchGate, 访问时间为 四月 22, 2026， [https://www.researchgate.net/publication/396529200_Multimodal_Chatbot_for_Emotion_Analysis_from_Text_and_Voice](https://www.researchgate.net/publication/396529200_Multimodal_Chatbot_for_Emotion_Analysis_from_Text_and_Voice)
    
44. Multimodal emotion recognition based on audiovisual text - IEEE Xplore, 访问时间为 四月 22, 2026， [https://ieeexplore.ieee.org/document/10900254/](https://ieeexplore.ieee.org/document/10900254/)
    
45. GitHub - Vanshika-Mittal/EmotionScope: IEEE Envision Project 2025- Multimodal Emotion Recognition in Conversation through Image and Text Fusion, 访问时间为 四月 22, 2026， [https://github.com/Vanshika-Mittal/EmotionScope](https://github.com/Vanshika-Mittal/EmotionScope)
    
46. A Comprehensive Review of Multimodal Emotion Recognition: Techniques, Challenges, and Future Directions - MDPI, 访问时间为 四月 22, 2026， [https://www.mdpi.com/2313-7673/10/7/418](https://www.mdpi.com/2313-7673/10/7/418)
    
47. Cross-modality fusion with EEG and text for enhanced emotion detection in English writing, 访问时间为 四月 22, 2026， [https://www.frontiersin.org/journals/neurorobotics/articles/10.3389/fnbot.2024.1529880/full](https://www.frontiersin.org/journals/neurorobotics/articles/10.3389/fnbot.2024.1529880/full)
    
48. MemoCMT: multimodal emotion recognition using cross-modal transformer-based feature fusion - PMC, 访问时间为 四月 22, 2026， [https://pmc.ncbi.nlm.nih.gov/articles/PMC11829003/](https://pmc.ncbi.nlm.nih.gov/articles/PMC11829003/)
    
49. Multimodal transformer augmented fusion for speech emotion recognition - Frontiers, 访问时间为 四月 22, 2026， [https://www.frontiersin.org/journals/neurorobotics/articles/10.3389/fnbot.2023.1181598/full](https://www.frontiersin.org/journals/neurorobotics/articles/10.3389/fnbot.2023.1181598/full)
    
50. Multimodal Fusion Techniques for Emotion Recognition Using Audio, Visual, and Physiological Signals - SOCIETY FOR COMMUNICATION AND COMPUTER TECHNOLOGIES, 访问时间为 四月 22, 2026， [https://ecejournals.in/index.php/NJSIP/article/view/348/719](https://ecejournals.in/index.php/NJSIP/article/view/348/719)
    
51. MemoCMT: multimodal emotion recognition using cross-modal ..., 访问时间为 四月 22, 2026， [https://nchr.elsevierpure.com/en/publications/memocmt-multimodal-emotion-recognition-using-cross-modal-transfor/](https://nchr.elsevierpure.com/en/publications/memocmt-multimodal-emotion-recognition-using-cross-modal-transfor/)
    
52. [2603.22345] Dynamic Fusion-Aware Graph Convolutional Neural Network for Multimodal Emotion Recognition in Conversations - arXiv, 访问时间为 四月 22, 2026， [https://arxiv.org/abs/2603.22345](https://arxiv.org/abs/2603.22345)
    
53. Robust Emotion Recognition Multimodal Using an Optimized Cross-Modal Data Fusion Framework - IIETA, 访问时间为 四月 22, 2026， [https://www.iieta.org/download/file/fid/192576](https://www.iieta.org/download/file/fid/192576)
    
54. On Multimodal Emotion Recognition for Human-Chatbot Interaction in the Wild - Computer Graphics Laboratory, 访问时间为 四月 22, 2026， [https://cgl.ethz.ch/Downloads/Publications/Papers/2024/Kov24c/Kov24c.pdf](https://cgl.ethz.ch/Downloads/Publications/Papers/2024/Kov24c/Kov24c.pdf)
    
55. Prompt engineering vs fine-tuning: Understanding the pros and cons - K2view, 访问时间为 四月 22, 2026， [https://www.k2view.com/blog/prompt-engineering-vs-fine-tuning/](https://www.k2view.com/blog/prompt-engineering-vs-fine-tuning/)
    
56. Prompt Tuning vs. Fine-Tuning—Differences, Best Practices, and Use Cases | Nexla, 访问时间为 四月 22, 2026， [https://nexla.com/ai-infrastructure/prompt-tuning-vs-fine-tuning/](https://nexla.com/ai-infrastructure/prompt-tuning-vs-fine-tuning/)
    
57. Large Language Models Understand and Can be Enhanced by Emotional Stimuli - arXiv, 访问时间为 四月 22, 2026， [https://arxiv.org/abs/2307.11760](https://arxiv.org/abs/2307.11760)
    
58. Emotional Framing in Prompts Modulates Large Language Model ..., 访问时间为 四月 22, 2026， [https://www.mdpi.com/2504-2289/10/4/102](https://www.mdpi.com/2504-2289/10/4/102)
    
59. Efficient LLM Customization (vs. Fine-Tuning & Prompt Engineering) | by Seahorse | Medium, 访问时间为 四月 22, 2026， [https://medium.com/@seahorse.technologies.sl/prompt-tuning-efficient-llm-customization-vs-fine-tuning-prompt-engineering-cc92e2a83097](https://medium.com/@seahorse.technologies.sl/prompt-tuning-efficient-llm-customization-vs-fine-tuning-prompt-engineering-cc92e2a83097)
    
60. Fine-Tuning, RAG, or Prompt Engineering? LLM Decision Guide - Moveo.AI, 访问时间为 四月 22, 2026， [https://moveo.ai/blog/fine-tuning-rag-or-prompt-engineering](https://moveo.ai/blog/fine-tuning-rag-or-prompt-engineering)
    
61. Estwld/empathetic_dialogues_llm · Datasets at Hugging Face, 访问时间为 四月 22, 2026， [https://huggingface.co/datasets/Estwld/empathetic_dialogues_llm](https://huggingface.co/datasets/Estwld/empathetic_dialogues_llm)
    
62. EmPO: Theory-Driven Dataset Construction for Empathetic Response Generation through Preference Optimization - arXiv, 访问时间为 四月 22, 2026， [https://arxiv.org/html/2406.19071v1](https://arxiv.org/html/2406.19071v1)
    
63. Empathetic Response Generation via Reinforcement Learning with Empathy Level Alignment and Semantic Relevance - MDPI, 访问时间为 四月 22, 2026， [https://www.mdpi.com/2073-8994/18/1/148](https://www.mdpi.com/2073-8994/18/1/148)
    
64. Prompt Engineering vs Fine Tuning: When to Use Each | Codecademy, 访问时间为 四月 22, 2026， [https://www.codecademy.com/article/prompt-engineering-vs-fine-tuning](https://www.codecademy.com/article/prompt-engineering-vs-fine-tuning)
    
65. Emotion meets coordination: Designing multi-agent LLMs for fine-grained user sentiment detection on social media - PMC, 访问时间为 四月 22, 2026， [https://pmc.ncbi.nlm.nih.gov/articles/PMC12885380/](https://pmc.ncbi.nlm.nih.gov/articles/PMC12885380/)
    
66. Choose fine-tuning or prompt engineering to customize an AI LLM - Macro 4, 访问时间为 四月 22, 2026， [https://www.macro4.com/blog/fine-tuning-vs-prompt-engineering-how-to-customize-your-ai-llm/](https://www.macro4.com/blog/fine-tuning-vs-prompt-engineering-how-to-customize-your-ai-llm/)
    
67. Emotional Support with LLM-based Empathetic Dialogue Generation - arXiv, 访问时间为 四月 22, 2026， [https://arxiv.org/html/2507.12820v1](https://arxiv.org/html/2507.12820v1)
    
68. RAG vs Fine-tuning vs Prompt Engineering: Everything You Need to Know | InterSystems, 访问时间为 四月 22, 2026， [https://www.intersystems.com/resources/rag-vs-fine-tuning-vs-prompt-engineering-everything-you-need-to-know/](https://www.intersystems.com/resources/rag-vs-fine-tuning-vs-prompt-engineering-everything-you-need-to-know/)
    
69. Was RLHF a Detour? Rethinking LLM Alignment with DPO | by Roshan K Tiwari - Medium, 访问时间为 四月 22, 2026， [https://medium.com/data-science-in-your-pocket/was-rlhf-a-detour-rethinking-llm-alignment-with-dpo-0e219f3184a2](https://medium.com/data-science-in-your-pocket/was-rlhf-a-detour-rethinking-llm-alignment-with-dpo-0e219f3184a2)
    
70. AI Agent Use Cases | IBM, 访问时间为 四月 22, 2026， [https://www.ibm.com/think/topics/ai-agent-use-cases](https://www.ibm.com/think/topics/ai-agent-use-cases)
    
71. RLHF vs DPO in LLM fine-tuning: 60+ patent analysis | PatSnap, 访问时间为 四月 22, 2026， [https://www.patsnap.com/resources/blog/articles/rlhf-vs-dpo-in-llm-fine-tuning-60-patent-analysis-2/](https://www.patsnap.com/resources/blog/articles/rlhf-vs-dpo-in-llm-fine-tuning-60-patent-analysis-2/)
    
72. How is prosody controlled in modern TTS systems? - Milvus, 访问时间为 四月 22, 2026， [https://milvus.io/ai-quick-reference/how-is-prosody-controlled-in-modern-tts-systems](https://milvus.io/ai-quick-reference/how-is-prosody-controlled-in-modern-tts-systems)
    
73. Controlling Emotion in Text-to-Speech with Natural Language Prompts - arXiv, 访问时间为 四月 22, 2026， [https://arxiv.org/html/2406.06406v1](https://arxiv.org/html/2406.06406v1)
    
74. How is prosody controlled in modern TTS systems? - Zilliz Vector Database, 访问时间为 四月 22, 2026， [https://zilliz.com/ai-faq/how-is-prosody-controlled-in-modern-tts-systems](https://zilliz.com/ai-faq/how-is-prosody-controlled-in-modern-tts-systems)
    
75. Make the Best AI Voices with Emotion (Realistic TTS) - YouTube, 访问时间为 四月 22, 2026， [https://www.youtube.com/watch?v=_cEcV96wQ1k](https://www.youtube.com/watch?v=_cEcV96wQ1k)
    
76. Best Emotional TTS APIs in 2026 - Softservice - Software Development Outsourcing, 访问时间为 四月 22, 2026， [https://softservice.org/software-development/text-to-speech-with-emotion/](https://softservice.org/software-development/text-to-speech-with-emotion/)
    
77. Towards Controllable Speech Synthesis in the Era of Large Language Models: A Survey, 访问时间为 四月 22, 2026， [https://arxiv.org/html/2412.06602v2](https://arxiv.org/html/2412.06602v2)
    
78. StyleTTS 2: Towards Human-Level Text-to-Speech through Style Diffusion and Adversarial Training with Large Speech Language Models - PMC, 访问时间为 四月 22, 2026， [https://pmc.ncbi.nlm.nih.gov/articles/PMC11759097/](https://pmc.ncbi.nlm.nih.gov/articles/PMC11759097/)
    
79. StyleTTS-ZS: Efficient High-Quality Zero-Shot Text-to-Speech Synthesis with Distilled Time-Varying Style Diffusion - arXiv, 访问时间为 四月 22, 2026， [https://arxiv.org/html/2409.10058v1](https://arxiv.org/html/2409.10058v1)
    
80. Emotional Text-To-Speech Based on Mutual-Information-Guided Emotion-Timbre Disentanglement - arXiv, 访问时间为 四月 22, 2026， [https://arxiv.org/html/2510.01722v1](https://arxiv.org/html/2510.01722v1)
    
81. EmoSteer-TTS: Fine-Grained and Training-Free Emotion-Controllable Text-to-Speech via Activation Steering - arXiv, 访问时间为 四月 22, 2026， [https://arxiv.org/html/2508.03543v1](https://arxiv.org/html/2508.03543v1)
    
82. Beyond Lip-Sync: Infusing Emotion into Avatars with AI-Driven Facial Expressions, 访问时间为 四月 22, 2026， [https://blogs.infosys.com/emerging-technology-solutions/digital-experience/beyond-lip-sync-infusing-emotion-into-avatars-with-ai-driven-facial-expressions.html](https://blogs.infosys.com/emerging-technology-solutions/digital-experience/beyond-lip-sync-infusing-emotion-into-avatars-with-ai-driven-facial-expressions.html)
    
83. The Ultimate Guide to Creating ARKit 52 Facial Blendshapes, 访问时间为 四月 22, 2026， [https://pooyadeperson.com/the-ultimate-guide-to-creating-arkits-52-facial-blendshapes/](https://pooyadeperson.com/the-ultimate-guide-to-creating-arkits-52-facial-blendshapes/)
    
84. Realistic Face Animations for AI Characters Using Convai, 访问时间为 四月 22, 2026， [https://convai.com/blog/realistic-face-animations-ai-characters-convai](https://convai.com/blog/realistic-face-animations-ai-characters-convai)
    
85. Audio2Face-3D: Audio-driven Realistic Facial Animation For Digital Avatars - arXiv, 访问时间为 四月 22, 2026， [https://arxiv.org/html/2508.16401v1](https://arxiv.org/html/2508.16401v1)
    
86. InstructAvatar - Yuchi Wang, 访问时间为 四月 22, 2026， [https://wangyuchi369.github.io/InstructAvatar/](https://wangyuchi369.github.io/InstructAvatar/)
    
87. Lip-Syncing Virtual AI Characters: Techniques, Integration, and Future Trends - Convai, 访问时间为 四月 22, 2026， [https://convai.com/blog/lip-syncing-virtual-ai-characters-techniques-integration-and-future-trends](https://convai.com/blog/lip-syncing-virtual-ai-characters-techniques-integration-and-future-trends)
    
88. Foster Meaningful Connections and Interactions with Audio To Expression for Meta Horizon OS, 访问时间为 四月 22, 2026， [https://developers.meta.com/horizon/blog/audio-to-expression-mixed-reality-blendshapes-movement-sdk-avatars/](https://developers.meta.com/horizon/blog/audio-to-expression-mixed-reality-blendshapes-movement-sdk-avatars/)
    
89. Affective Computing and Emotional Data: Challenges and Implications in Privacy Regulations, The AI Act, and Ethics in Large Language Models - arXiv, 访问时间为 四月 22, 2026， [https://arxiv.org/html/2509.20153v2](https://arxiv.org/html/2509.20153v2)
    
90. Cultural Differences in People's Reactions and Applications of Robots, Algorithms, and Artificial Intelligence | Management and Organization Review - Cambridge University Press, 访问时间为 四月 22, 2026， [https://www.cambridge.org/core/journals/management-and-organization-review/article/cultural-differences-in-peoples-reactions-and-applications-of-robots-algorithms-and-artificial-intelligence/EE491FDF4C4773AB97D71C89545DF07C](https://www.cambridge.org/core/journals/management-and-organization-review/article/cultural-differences-in-peoples-reactions-and-applications-of-robots-algorithms-and-artificial-intelligence/EE491FDF4C4773AB97D71C89545DF07C)
    
91. Cultural Display Rules – Culture and Psychology - Maricopa Open Digital Press, 访问时间为 四月 22, 2026， [https://open.maricopa.edu/culturepsychology/chapter/cultural-display-rules/](https://open.maricopa.edu/culturepsychology/chapter/cultural-display-rules/)
    
92. Cultural Similarities and Differences in Display Rules! - David Matsumoto, 访问时间为 四月 22, 2026， [http://www.davidmatsumoto.com/content/1990%20Cultural%20Similarities%20and%20Differences%20in%20Display%20Rules.pdf](http://www.davidmatsumoto.com/content/1990%20Cultural%20Similarities%20and%20Differences%20in%20Display%20Rules.pdf)
    
93. Expressing Social Emotions: Misalignment Between LLMs and Human Cultural Emotion Norms - arXiv, 访问时间为 四月 22, 2026， [https://arxiv.org/html/2604.16757v1](https://arxiv.org/html/2604.16757v1)
    
94. Accuracy of spontaneous dynamic teacher emotion recognition by Japanese college students - Frontiers, 访问时间为 四月 22, 2026， [https://www.frontiersin.org/journals/education/articles/10.3389/feduc.2025.1536227/full](https://www.frontiersin.org/journals/education/articles/10.3389/feduc.2025.1536227/full)
    
95. Cross-Cultural Emotion Recognition in AI: Enhancing Multimodal NLP for Empathetic Interaction - ResearchGate, 访问时间为 四月 22, 2026， [https://www.researchgate.net/publication/392414598_Cross-cultural_emotion_recognition_in_AI_Enhancing_multimodal_NLP_for_empathetic_interaction](https://www.researchgate.net/publication/392414598_Cross-cultural_emotion_recognition_in_AI_Enhancing_multimodal_NLP_for_empathetic_interaction)
    
96. Studying the impact of emotion-AI in cross-cultural communication on the effectiveness of global media - Frontiers, 访问时间为 四月 22, 2026， [https://www.frontiersin.org/journals/computer-science/articles/10.3389/fcomp.2025.1565869/full](https://www.frontiersin.org/journals/computer-science/articles/10.3389/fcomp.2025.1565869/full)
    
97. AI chatbots and digital companions are reshaping emotional connection, 访问时间为 四月 22, 2026， [https://www.apa.org/monitor/2026/01-02/trends-digital-ai-relationships-emotional-connection](https://www.apa.org/monitor/2026/01-02/trends-digital-ai-relationships-emotional-connection)
    
98. Teaching AI Ethics 2026: Emotions and Social Chatbots - Leon Furze, 访问时间为 四月 22, 2026， [https://leonfurze.com/2026/01/28/teaching-ai-ethics-2026-emotions-and-social-chatbots/](https://leonfurze.com/2026/01/28/teaching-ai-ethics-2026-emotions-and-social-chatbots/)
    
99. Investigating Affective Use and Emotional Well-being on ChatGPT - arXiv, 访问时间为 四月 22, 2026， [https://arxiv.org/html/2504.03888v1](https://arxiv.org/html/2504.03888v1)
    
100. Architecture of stateful AI emotion vs. internal state | by Electric Wolfe Marshmallow Hypertext | Medium, 访问时间为 四月 22, 2026， [https://medium.com/@marshmallow-hypertext/how-ai-feelings-work-and-why-it-matters-for-real-safety-8de5978d4fac](https://medium.com/@marshmallow-hypertext/how-ai-feelings-work-and-why-it-matters-for-real-safety-8de5978d4fac)
    
101. New study: AI chatbots systematically violate mental health ethics standards, 访问时间为 四月 22, 2026， [https://www.brown.edu/news/2025-10-21/ai-mental-health-ethics](https://www.brown.edu/news/2025-10-21/ai-mental-health-ethics)
    
102. Charting the evolution of artificial intelligence mental health chatbots from rule‐based systems to large language models: a systematic review - PMC, 访问时间为 四月 22, 2026， [https://pmc.ncbi.nlm.nih.gov/articles/PMC12434366/](https://pmc.ncbi.nlm.nih.gov/articles/PMC12434366/)
    
103. The Ethics of Emotional Artificial Intelligence: A Mixed Method Analysis - PMC - NIH, 访问时间为 四月 22, 2026， [https://pmc.ncbi.nlm.nih.gov/articles/PMC10555972/](https://pmc.ncbi.nlm.nih.gov/articles/PMC10555972/)
    
104. Both ends of artificial intelligence impacting privacy: a review of violation and protection, 访问时间为 四月 22, 2026， [https://pmc.ncbi.nlm.nih.gov/articles/PMC12957209/](https://pmc.ncbi.nlm.nih.gov/articles/PMC12957209/)
    
105. The Time to (AI) Act is Now: A Practical Guide to Emotion Recognition Systems Under the AI Act - WILLIAM FRY, 访问时间为 四月 22, 2026， [https://www.williamfry.com/knowledge/the-time-to-ai-act-is-now-a-practical-guide-to-emotion-recognition-systems-under-the-ai-act/](https://www.williamfry.com/knowledge/the-time-to-ai-act-is-now-a-practical-guide-to-emotion-recognition-systems-under-the-ai-act/)
    
106. 2026 AI Laws Update: Key Regulations and Practical Guidance - Gunderson Dettmer, 访问时间为 四月 22, 2026， [https://www.gunder.com/en/news-insights/insights/2026-ai-laws-update-key-regulations-and-practical-guidance](https://www.gunder.com/en/news-insights/insights/2026-ai-laws-update-key-regulations-and-practical-guidance)
    
107. AI Rules Are Changing: Key Regulatory Updates for 2025 & 2026 | Compliance & Risks, 访问时间为 四月 22, 2026， [https://www.youtube.com/watch?v=hvlTWt30CEw](https://www.youtube.com/watch?v=hvlTWt30CEw)
    
108. High-level summary of the AI Act | EU Artificial Intelligence Act, 访问时间为 四月 22, 2026， [https://artificialintelligenceact.eu/high-level-summary/](https://artificialintelligenceact.eu/high-level-summary/)
    
109. EU Commission Issues Guidelines on Prohibited AI Practices Under EU AI Act, 访问时间为 四月 22, 2026， [https://www.wsgrdataadvisor.com/2025/02/eu-commission-issues-guidelines-on-prohibited-ai-practices-under-eu-ai-act/](https://www.wsgrdataadvisor.com/2025/02/eu-commission-issues-guidelines-on-prohibited-ai-practices-under-eu-ai-act/)
    
110. The Price of Emotion: Privacy, Manipulation, and Bias in Emotional AI, 访问时间为 四月 22, 2026， [https://www.americanbar.org/groups/business_law/resources/business-law-today/2024-september/price-emotion-privacy-manipulation-bias-emotional-ai/](https://www.americanbar.org/groups/business_law/resources/business-law-today/2024-september/price-emotion-privacy-manipulation-bias-emotional-ai/)
    
111. Annex III: High-Risk AI Systems Referred to in Article 6(2) | EU Artificial Intelligence Act, 访问时间为 四月 22, 2026， [https://artificialintelligenceact.eu/annex/3/](https://artificialintelligenceact.eu/annex/3/)
    
112. Navigating the AI Act | Shaping Europe's digital future - European Union, 访问时间为 四月 22, 2026， [https://digital-strategy.ec.europa.eu/en/faqs/navigating-ai-act](https://digital-strategy.ec.europa.eu/en/faqs/navigating-ai-act)
    
113. AI Act | Shaping Europe's digital future - European Union, 访问时间为 四月 22, 2026， [https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai](https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai)
