# 《领域驱动设计》精读提取笔记（第10章–第12章）
> 源文本：scripts/docs/notes/DDD-OCR.txt，行 7827–10413（PDF 第190–249页；PDF 页码取自 OCR 中的 [PDF第X页] 标记）。忠实提取，不做裁决；OCR 噪声（错字/断行/页眉页脚）按上下文理解，引文保留原文措辞，OCR 明显错字随注「——OCR『X』应为『Y』」。共 67 条：第10章 45 条（10-1–10-45）/ 第11章 12 条（11-1–11-12）/ 第12章 10 条（12-1–12-10）。供上游 Agent 对照工程规约判定缺口。

## 第10章 柔性设计（OCR 7827–9415，PDF 190–227）

### 10-1 章开篇：柔性设计的动机、两种开发角色与适用时机｜PDF190–191｜行7827–7874
- 「7件的最终目的是为用户服务。但首先它必须为开发人员服务。」（7830）——OCR「7件」应为「软件」
- 「为了使项目能够随着开发工作的进行加速前进，而不会由于它自己的老化停滞不前，设计必须要让人们乐于使用，而且易于做出修改。这就是柔性设计（supple design）。」（7841–7842）
- 「很多过度设计（overengineering）借着柔性设计的名义而自认为是正当的。但是，过多的抽象层和间接设计常常成为项目的绊脚石。」（7853–7854）
- 「开发人员扮演着两个角色，而设计必须要为这两个角色服务。同一个人可能会同时承担这两种角色，甚至在几分钟之内来回变换角色，但角色与代码之间的关系是不同的。一个角色是客户开发人员，负责将领域对象组织成应用程序代码或其他领域层代码，以便发挥设计的功能。」（7858–7860）
- 「同样重要的是，设计也必须那些修改代码的开发人员服务。」（7864）——OCR 漏「为」字，应为「设计也必须为那些修改代码的开发人员服务」
- 「但是，当复杂性阻碍了项目的前进时，就需要仔细修改最关键、最复杂的地方，使之变成一个柔性设计，这样才能突破复杂性带给我们的限制，而不会陷人遗留代码维护的麻烦中。」（7869–7871）——OCR「陷人」应为「陷入」

### 10-2 §10.1 模式：INTENTION-REVEALING INTERFACES——问题：认识过载与封装失效（含图10-1）｜PDF191–193｜行7875–7935
- 「在领域驱动的设计中，我们希望看到有意义的领域逻辑。如果代码只是在执行规则后得到结果，而没有把规则显式地表达出来，那么我们就不得一步一步地去思考软件的执行步骤。」（7876–7877）——OCR「不得」应为「不得不」
- 图10-1（7889–7917）「一些有助于获得柔性设计的模式」：节点含 INTENTION-REVEALING INTERFACE、SIDE-EFFECT-FREE FUNCTION、ASSERTION、UBIQUITOUS LANGUAGE、MODEL-DRIVEN DESIGN、CLOSURE OF OPERATION、STANDALONE CLASS、CONCEPTUAL CONTOURS，连线标注「简化解释」「减小修改的代价」「使这二者可以安全组合」「使之安全且简单」「使副作用可以暴露出来」「通过它来表示模型」「可以使用」「~从它提取」——图中英文经 OCR 有乱码：「UalqurTous LANGUAGE」应为「UBIQUITOUS LANGUAGE」、「MopEL-DRIVEN DESIGN」应为「MODEL-DRIVEN DESIGN」，另混入页码数字 243/244/246/247/248（原图箭头上的交叉引用页码），部分标注残缺
- 「但是，客户开发人员要想有效地使用对象，必须知道对象的一些信息，如果接口没有告诉开发人员这些信息，那么他就必须深人研究对象的内部机制，以便理解细节。阅读客户代码的人也需要做同样的事情。这样就失去了封装的大部分价值。我们需要避免出现“认识过载”的问题。」（7918–7920）——OCR「深人」应为「深入」
- 「如果开发人员为了使用一个组件而必须要去研究它的实现，那么就失去了封装的价值。」（7924）
- 「当某个人开发的对象或操作被别人使用时，如果使用这个组件的新的开发者不得不根据其实现来推测其用途，那么他推测出来的可能并不是那个操作或类的主要用途。如果这不是那个组件的用途，虽然代码暂时可以工作，但设计的概念基础已经被误用了，两位开发人员的意图也是背道而驰。」（7925–7928）
- 「当我们把概念显式地建模为类或方法时，为了真正从中获取价值，必须为这些程序元素赋予一个能够反映出它们的概念的名字。类和方法的名称为开发人员之间的沟通创造了很好的机会，也能够改善系统的抽象。」（7929–7935，跨页断行已拼接）

### 10-3 §10.1 续：释意命名与模式陈述（因此）｜PDF193｜行7936–7948
- 「Kent Beck曾经提出通过INTENTION-REVEALING SELECTOR（释意命名选择器）来选择方法的名称，使名称表达出其目的［Beck 1997］。」（7936–7937）
- 「设计中的所有公共元素共同构成了接口，每个元素的名称都提供了一次揭示设计意图的机会。类型名称、方法名称和参数名称组合在一起，共同形成了一个INTENTION-REVEALING INTERFACE（释意接口）。」（7937–7939）
- 「在命名类和操作时要描述它们的效果和目的，而不要表露它们是通过何种方式达到目的的。这样可以使客户开发人员不必去理解内部的细节。这些名称应该与UBIQUITOUS LANGUAGE保持一致，以便团队成员可以迅速推断出它们的意义。」（7941–7943）
- 「在创建一个行为之前先为它编写一个测试，这样可以促使你站在客户开发人员的角度上来思考它。」（7943–7944）
- 「所有复杂的机制都应该封装到抽象接口的后面，接口只表明意图，而不表明方式。」（7945）
- 「在领域的公共接口中，可以把关系和规则表述出来，但不要说明规则是如何实施的，可以把事件和动作描述出来，但不要描述它们是如何执行的，可以给出方程式，但不要给出解方程式的数学方法。可以提出问题，但不要给出获取答案的方法。」（7946–7948）

### 10-4 §10.1 示例：重构调漆应用程序——初始设计与第一版测试｜PDF193–194｜行7949–7994
- 「paint （Paint）方法的行为根本猜不出，想知道它的唯一方法就是阅读代码。」（7960）——图10-2（7953–7959）：Paint 类属性「v:double」「r：int」「y：int」「b：int」，操作「paint（Paint）」
- 代码转述（7961–7966）：public void paint(Paint paint) 方法体首行 v=v+paint.getV()（体积相加），其余为行内注释「Omitted many lines of complicated color mixing logic // ending with the assignment of new 工.b,and y values.」——OCR「工.b」应为「r,b」，即对新 r、b、y 值的赋值
- 「从代码上看，这个方法是把两种油漆（Paint）混合到一起，结果是油漆的体积增加了，并变为混合颜色。」（7967–7968）
- 第一版测试转述（7978–7990，JUnit）：Paint yellow = new Paint(100.0,0,50,0) 纯黄、Paint blue = new Paint(100.0,0,0,50) 纯蓝，执行 yellow.paint(blue)，断言体积 200.0（getV，容差 0.01）及 green paint（getB()=25、getY()=25、getR()=0）——OCR「volune」应为「volume」、「Yellow.paint/getV/getx」大小写应为「yellow」、「getx」应为「getY」
- 「通过这个测试只是一个起点，这无法令我们满意，因为这段测试代码并没有告诉我们这个方法都做了什么。」（7991–7992）
- 「最初，这个测试会失败。实际上，它甚至不能编译。我们编写它的目的是从客户开发人员的角度来研究一下Paint对象的接口设计。」（7993–7994）

### 10-5 §10.1 示例（续）：客户视角的第二版测试与 mixIn 重构（图10-3），及 10.1 收束｜PDF194–195｜行7995–8037
- 第二版测试转述（7995–8013）：ourPaint = new Paint(100.0,0,50,0)，Paint blue = new Paint(100.0,0,0,50)，调用 ourPaint.mixIn(blue)，断言 getVolume()=200.0（容差 0.01）、getBlue()=25、getYellow()=25、getRed()=0——接口由 paint(Paint)/getV 改为客户视角的 mixIn(Paint)/getVolume/getBlue/getYellow/getRed（注释被 OCR 断行为多行；「assertEquvals」应为「assertEquals」）
- 「花时间编写这样的测试是非常必要的，因为它可以反映出我们希望以哪种方式与这些对象进行交互。在这之后，我们重构Paint类，使它通过测试。如图10-3所示。」（8014–8015）
- 图10-3（8024–8030）：Paint 类重构前（paint（Paint））与重构后（含属性与 mixin（Paint））的对比——属性名 OCR 残缺（如「Baleyaml」无法还原），「mixin」应为「mixIn」
- 「新的方法名称可能不会告诉读者有关混合另一种油漆（Paint）的效果的所有信息（要达到这个目的需要使用断言，接下来我们就会讨论它）。但这个名称为读者提供了足够多的线索，使读者可以开始使用这个类，特别是从测试提供的示例开始。而且它还使客户代码的阅读者能够理解客户的意图。」（8016–8019）
- 「整个子领域可以被划分到独立的模块中，并用一个接口把它们封装起来（这个接口表达了其用途）。这种方法可以使我们把注意力集中在项目上，并控制大型系统的复杂性，这些内容将在第15章中的COHESIVE MECHANISM和GENERIC SUBDOMAIN部分进行更多的讨论。」（8032–8034）
- 「在接下来的两个模式中，我们将介绍如何令一个方法的执行结果变得易于预测。复杂的逻辑可以在SIDE-EFFECT-FREE FUNCTION中安全地执行，而改变系统状态的方法可以用ASSERTION来刻画。」（8035–8037）

### 10-6 §10.2 模式：SIDE-EFFECT-FREE FUNCTION——命令、查询与副作用｜PDF195｜行8038–8059
- 「我们可以宽泛地把操作分为两个大的类别：命令和查询。查询是从系统获取信息，查询的方式可能只是简单地访问变量中的数据，也可能是用这些数据执行计算。命令（也称修改器）是修改系统的操作（举一个简单的例子，设置变量）。」（8040–8042）
- 「在标准英语中，“副作用”这个词暗示着“意外的结果”，但在计算机科学中，任何对系统状态产生的影响都叫副作用。这里为了便于讨论，我们把它的含义缩小一下，任何对未来操作产生影响的系统状态的改变都可以称为副作用。」（8042–8044）
- 「大多数操作都会调用其他的操作，而后者又会调用另外一些操作。一旦形成这种任意深度的嵌套，就很难预测调用一个操作将要产生的所有后果。第二层和第三层操作的影响可能并不是客户开发人员有意而为之的，于是它们就变成了完全意义上的副作用。在一个复杂的设计中，元素之间的交互同样也会产生无法预料的结果。副作用这个词强调了这种交互的不可避免性。」（8046–8050）
- 「多个规则或计算组合的相互作用所产生的结果是很难预测的。开发人员在调用一个操作时，为了预测操作的结果，必须理解它的实现以及所有派生操作的实现。如果开发人员不得不“揭开接口的面纱”，那么接口的抽象的作用就受到了限制。如果没有了可以安全地预见到结果的抽象，开发人员就必须限制“组合爆炸”，这就限制了系统行为的丰富性。」（8051–8054）
- 脚注：「① 组合爆炸 （combinatory explosion），源自离散数学的术语，是指随着问题中元素的增加，所出现的可能组合数剧烈增加。—一译者注」（8055–8056）——OCR「—一」应为「——」

### 10-7 §10.2 续：函数、命令/查询分离与 VALUE OBJECT；模式陈述（因此）｜PDF196｜行8061–8090
- 「返回结果而不产生副作用的操作称为函数。一个函数可以被多次调用，每次调用都返回相同的值。一个函数可以调用其他函数，而不必担心这种嵌套的深度。函数比那些有副作用的操作更易于测试。由于这些原因，使用函数可以降低风险。」（8065–8067）
- 「显然，在大多数软件系统中，命令的使用都是不可避免的，但有两种方法可以减少命令产生的问题。首先，可以把命令和查询严格地放在不同的操作中。确保导致状态改变的方法不返回领域数据，并尽可能保持简单。在不引起任何可观测到的副作用的方法中执行所有查询和计算（［Meyer 1988］）。」（8068–8071）
- 「第二，总是有一些替代的模型和设计，它们不要求对现有对象做任何修改。相反，它们创建并返回一个VALUE OBJECT，用于表示计算结果。这是一种很常见的技术，在接下来的示例中我们就会演示它的使用。VALUE OBJECT可以在响应一次查询中被创建和传递，然后被丢弃—不像ENTITY，实体的生命周期是受到严格管理的。」（8072–8075）
- 「VALUE OBJECT是不可变的，这意味着除了在创建期间调用的初始化程序之外，它们的所有操作都是函数。像函数一样，VALUE OBJECT使用起来很安全，测试也很简单。」（8076–8077）
- 「因此：尽可能把程序的逻辑放到函数中，因为函数是只返回结果而不产生明显副作用的操作。严格地把命令（引起明显的状态改变的方法）隔离到不返回领域信息的，非常简单的操作中。当发现了一个非常适合承担复杂逻辑职责的概念时，就可以把这个复杂逻辑移到VALUE OBJECT中，这样可以进一步控制副作用。」（8083–8087）
- 「SIDE-EFFECT-FREE FUNCTION，特别是不变的VALUE OBJECT，允许我们安全地对多个操作进行组合。当通过一个INTENTION-REVEALING INTERFACE把一个FUNCTION呈现出来的时候，开发人员就可以在无需理解其实现细节的情况下使用它。」（8088–8090）

### 10-8 §10.2 示例：再次重构调漆应用程序——mixIn 的副作用（图10-4/10-5）｜PDF196–198｜行8091–8150
- 「一家油漆商店的程序能够客户显示出标准调漆的结果。我们继续前面的例子，下面是重构后得到的那个类：」（8093–8094）——OCR 漏「向」，应为「能够向客户显示出」
- 代码转述（8095–8097，注释跨页接 8102–8103）：public void mixIn(Paint other) { volume = volume.plus(other.getVolume()); // Many lines of complicated color-mixing logic // ending with the assignment of new red, blue, and yellow values. }——OCR「mixin」应为「mixIn」、「1ines」应为「lines」、「1/」应为「//」
- 图10-4（8104–8113）：Paint 类——volume:double、red:int、yellow:int、blue:int、mixin（Paint）；附注「捕获到的知识：颜料有红、黄、蓝三原色（挑剔的人认为三原色是洋红、黄和青色）」（8110–8112）
- 图10-5（8114–8141）「mixIn（）方法的副作用」：mixin（paint2）将 paint1（1/2 gallon，shade of yellow）变为 1 gallon shade of green，paint2（1/2 gallon，shade of blue）保持不变；图内注「这里应该产生什么变化呢？原来的开发人员似乎对它不感兴趣，而且一直没有指定。」（8125–8130）——OCR「paintl」应为「paint1」
- 「mixin（）方法中发生了很多事情，但这个设计确实遵循了“修改和查询分离”这条原则。有一点需要注意（下面会具体讨论），这里并没有对paint2对象的体积（它是mixIn（）方法的一个参数）做过多的考虑。操作不改变Paint 2的体积，在这个概念模型的上下文中，这看起来并不是十分合乎逻辑。」（8142–8145）——OCR「mixin（）」应为「mixIn（）」
- 「在这个领域中，颜色是一个重要的概念。让我们试着把它变成一个显式的对象。它应该叫什么名字呢？首先想到的就是Color（颜色），但我们通过先前的知识消化已经认识到了一个重要的知识，即油漆的调色与我们所熟悉的RGB调色是不同的。名称必须反映出这一点。」（8148–8150）

### 10-9 §10.2 示例（续）：Pigment Color 值对象与 mixedWith（图10-6/10-7/10-8）｜PDF198–199｜行8155–8226
- 图10-6（8158–8166）：Paint（volume:double、mixin（Paint））关联 Pigment Color（red:int、yellow:int、biue:int）——OCR「biue」应为「blue」
- 「把Pigment Color（颜料颜色）分离出来之后，确实比先前表达了更多信息，但计算还是相同的，仍然是在mixIn（）方法中进行计算。当把颜色数据移出来后，与这些数据有关的行为也应该一起移出来。但是在做这件事之前，要注意Pigment Color是一个VALUE OBJECT。因此，它应该是不可变的。当我们调漆时，Paint对象本身被改变了，它是一个具有生命周期的实体。相反，表示某个色调（例如黄色）的Pigment Color则一直表示那种颜色。调漆的结果是产生一个新的Pigment Color对象，用于表示新的颜色。」（8167–8172）
- 图10-7（8173–8181）：Paint（volume:double、mixIn（Paint））与 Pigment Color——后者新增操作「mixedWith（Pigment Color, double）：Pigment Color」（8180）——OCR 属性行「yellow:ir」「lue:in」残缺，应为 yellow:int、blue:int
- 代码转述（8182–8198）：public class PigmentColor { public PigmentColor mixedWith(PigmentColor other, double ratio) { // Many lines of complicated color-mixing logic // ending with the creation of a new PigmentColor object // with appropriate new red, blue, and yellow values. } }；public class Paint { public void mixIn(Paint other) { volume = volume + other.getVolume(); double ratio = other.getVolume() / volume; pigmentColor = pigmentColor.mixedWith(other.pigmentColor(), ratio); } }——OCR「Pigmentcoloz」「Public mixedwith」「other.pigmentColor（）.ratio」等应为「PigmentColor」「public mixedWith」「other.pigmentColor(), ratio」
- 图10-8（8201–8222）：mixedWith(color2)——color1（shade of yellow）与 color2（shade of blue）生成新对象 color3（shade of green），图内注「创建一个新的VALUE OBJECT，现有对象保持不变。」（8213–8216）——OCR「slor2」应为「color2」、「color 3 9：」应为「color3:」
- 「现在，Paint中的代码已经尽可能简单了。新的PigmentColor类捕获了知识，并显式地把这些知识表达出来，而且它还提供了一个SIDE-EFFECT-FREE FUNCTION，函数的计算结果很容易理解，也很容易测试，因此可以安全地使用或与其他操作进行组合。由于它的安全性很高，因此复杂的调色逻辑真正被封装起来了。使用这个类的开发人员不必理解其实现。」（8223–8226）

### 10-10 §10.3 模式：ASSERTION——问题、契约式设计与断言类别｜PDF199–200｜行8227–8260
- 「把复杂的计算封装到SIDE-EFFECT-FREE FUNCTION中可以简化问题，但实体仍然会留有一些有副作用的命令，使用这些ENTITY的人必须了解使用这些命令的后果。在这种情况下，使用ASSERTION（断言）可以把副作用明确地表示出来，使它们更易于处理。」（8229–8231）
- 「确实，一条不包含复杂计算的命令只需查看一下就能够理解。但是，在一个软件设计中，如果较大的部分是由较小部分构成的，那么一个命令可能会调用其他命令。开发人员在使用高层命令时，必须了解每个底层命令所产生的后果，这时封装也就没有什么价值了。而且，由于对象接口并不会限制副作用，因此实现相同接口的两个子类可能会产生不同的副作用。使用它们的开发人员需要知道哪个副作用是由哪个子类产生的，以便预测后果。这样，抽象和多态也就失去了意义。」（8233–8238）
- 「如果操作的副作用仅仅是由它们的实现隐式定义的，那么在一个具有大量相互调用关系的系统中，起因和结果会变得一团槽。理解程序的唯一方式就是沿着分支路径来跟踪程序的执行。封装完全失去了价值。跟踪具体的执行也使抽象失去了意义。」（8239–8241）——OCR「一团槽」应为「一团糟」
- 「INTENTION-REVEALING INTERFACE可以起到一部分作用，但这样的接口只能非正式地给出操作的用途，这常常是不够的。“契约式设计”（design by contract）向前推进了一步，通过给出类和方法的“断言”使开发人员知道肯定会发生的结果。」（8250–8252）
- 「简言之，“后置条件”描述了一个操作的副作用，也就是调用一个方法之后必然会发生的结果。“前置条件”就像是合同条款，即了满足后置条件而必须要满足的前置条件。类的固定规则规定了在操作结束时对象的状态。也可以把AGGREGATE作为一个整体来为它声明固定规则，这些都是严格定义的完整性规则。」（8252–8256）——OCR「即了满足」应为「为了满足」
- 「所有这些断言都描述了状态，而不是过程，因此它们更易于分析。类的固定规则在描述类的意义方面起到帮助作用，并且使客户开发人员能够更准确地预测对象的行为，从而简化他们的工作。如果你确信后置条件的保证，那么就不必考虑方法是如何工作的。断言应该已经把调用其他操作的效果考虑在内了。」（8257–8260）

### 10-11 §10.3 模式陈述：单元测试与概念内聚模型｜PDF200｜行8261–8274
- 「因此：把操作的后置条件和类及AGGREGATE的固定规则表述清楚。如果在你的编程语言中不能直接编写ASSERTION，那么就把它们编写成自动的单元测试。还可以把它们写到文档或图中（如果符合项目开发风格的话）。」（8261–8264）
- 「寻找在概念上内聚的模型，以便使开发人员更容易推出预期的ASSERTION，从而加快学习过程并避免代码矛盾。」（8265–8266）——OCR「推出」疑应为「推断」
- 「尽管很多面向对象的语言目前都不支持直接使用ASSERTION，但ASSERTION仍然不失为一种功能强大的设计方法。自动单元测试在一定程度上弥补了缺乏语言支持带来的不足。由于ASSERTION只声明状态，而不声明过程，因此很容易编写测试。测试首先设置前置条件，在执行之后，再检查后置条件是否被满足。」（8267–8270）
- 「把固定规则，前置条件和后置条件清楚地表述出来，这样开发人员就能够理解使用一个操作或对象的后果。从理论上讲，如果一组断言之间互不矛盾，那么就可以使用。但人的大脑并不会一丝不苟地把这些断言编译到一起。人们会推断和补充模型的概念，因此找到一个既易于理解又满足应用程序需求的模型是至关重要的。」（8271–8274）

### 10-12 §10.3 示例：回到调漆应用程序——参数的命运与后置条件（图10-9）｜PDF200–201｜行8275–8303
- 「在前面的示例中，我们曾注意到：在Paint类中mixIn（Paint）操作的参数到底会发生什么变化，这还存在着一些不明之处。」（8277–8278）
- 「接受者（即被混合的油漆）的体积增加了的体积就是参数的体积。根据我们对油漆的一般理解，这个混合过程应该使另一种油漆减少同样的体积，把它的体积减为零或完全删除。目前的实现并没有修改这个参数，而修改参数无疑是有产生副作用的风险的。」（8279–8280、8285，跨页断行已拼接）——OCR「体积增加了的体积」疑应为「体积增加的量」
- 图10-9（8286–8295）：Paint（volume:double、mixIn（Paint））与 Pigment Color（red:int、yellow:int、blue:int、mixed With（Pigment Color, double）: Pigment Color）——与图10-7 相同的类图重印，OCR「yellow :im」应为「yellow:int」
- 「第一步，我们先把mixIn（）方法的后置条件声明如下：在p1.mixIn（P2）之后：P1.volume增加p2.volume的量；p2.volume不变。」（8296–8299）——OCR「mixIn（P2）」大小写混乱，应为「p1.mixIn（p2）」
- 「问题在于开发人员将会犯错，因这些属性与实际概念不符。简单的修改方法是让另一种油漆的体积变为零。虽然修改参数不是一种好的行为，但这里的修改简单而直观。我们可以声明一个固定规则：混合之后油漆的总体积保持不变。」（8300–8303）——OCR「犯错，因这些」应为「犯错，因为这些」

### 10-13 §10.3 示例（续）：新发现、丢失概念与职责分离｜PDF201｜行8304–8318
- 「但先等一下！当开发人员考虑这种选择时，他们有了一个新发现。最初的设计人员这样设计原来是有充分理由的。程序在最后会报告被混合之前的油漆清单。毕竟，这个程序的最终目的是帮助用户弄清楚把哪几种油漆混合到一起。」（8304–8306）
- 「因此，如果要使体积模型的逻辑保持一致，那么它就无法满足这个应用程序的需求了。这看上去是一种进退两难的境况。我们是否仍使用这个不合常理的后置条件，并为了弥补这个不足而清楚地说明这样做的理由呢？世界上并不是一切事物都是直观的，有时直观是最好的答案。但在这种情况下……这种尴尬局面似乎是由于丢失概念而造成的。让我们去寻找一个新的模型。」（8307–8310）——OCR「但在这种情况下……」原文为「但在」（8309–8310 行接「这个例子中」，跨行直录；引文按 OCR 原文保留）
- 「我们在寻找更好的模型的时候，会比原来的设计人员更有优势，因为我们在研究的过程中消化了更多知识，而且通过重构得到了更深层的理解。例如，我们用一个VALUE OBIECT上的SIDE-EFFECT-FREE FUNCTION来计算颜色。这意味着可以在任何需要的时候重复进行这个计算。我们应该利用这种优势。」（8312–8315）——OCR「VALUE OBIECT」应为「VALUE OBJECT」
- 「我们似乎为Paint分配了两种不同的基本职责。让我们试着把它们分开。现在只有一个命令，即mixIn（）。从对模型的直观理解可以看出，它只是把•个对象加人到一个集合中。所有其他操作都是SIDE-EFFECT-FREE FUNCTION。」（8316–8318）——OCR「把•个对象加人到」应为「把一个对象加入到」

### 10-14 §10.3 示例（续）：图10-10 Mixed Paint、单元测试与模式小结｜PDF201–202｜行8319–8361
- 「下面的测试方法（使用了JUnit测试框架）用来确认图10-10中列出的一个ASSERTION是否满足：」（8319）
- 图10-10（8326–8344）：Mixed Paint（getVolume():double、getColor():Pigment Color、mixIn（Stock Paint）、stockConstituents（））关联 constituents * Stock Paint（volume:double、color:Pigment Color）——OCR「getVolumel」应为「getVolume」、「mixin/mixln」应为「mixIn」；注「mixln（Stock Paint）只是把一个新的paint对象添加到配料集合中。getVolume（）返回配料体积的总数。getColor（）使用Pigment Color mixed With（）来计算配料颜色的混合，并返回结果值。」（8338–8342）
- testMixingVolume 测试代码（8345–8354）：public void testMixingvolume（）中新建 Pigmentcolor yellow（0,50,0）与 blue（0,0,50）、StockPaint paint1（1.0, yellow）与 paint2（1.5, blue），MixedPaint mix 后依次 mixIn 两罐油漆，assertEquals（2.5, mix.getVolume（）, 0.01）——OCR「Pigmentcolor/testMixingvolume」应为「PigmentColor/testMixingVolume」，全角分号「）：」应为「);」
- 「这个模型捕提并传递了更多领域知识。固定规则和后置条件符合常识，这使得它们更易于维」（8356；句尾「护和使用。」被 OCR 错位至前一行 8355 行首）——OCR「捕提」应为「捕捉」
- 「INTENTION-REVEAL.ING INTERFACE清楚地表明了用途，SIDE-EFFECT-FREE FUNCTION和ASSERTION使我们能够更准确地预测结果，因此封装和抽象更加安全。可重组元素的下一个因素是有效的分解⋯⋯」（8359–8361）——OCR「INTENTION-REVEAL.ING」应为「INTENTION-REVEALING」

### 10-15 §10.4 模式：CONCEPTUAL CONTOUR——粒度困境与领域一致性｜PDF203｜行8366–8390
- 「有时，人们会对功能进行更细的分解，以便灵活地组合它们，有时要把功能组合成大块，以便封装复杂性。有时，人们为了使所有类和操作都具有相似的规模而寻找一种一致的粒度。这些方法都过于简单了，并不能作为通用的规则。」（8368–8370）
- 「如果把模型或设计的所有元素都放在一个整体的大结构中，那么它们的功能就会发生重复。外部接口无法全部给出客户可能关心的信息。由于不同的概念被混合在一起，它们的意义变得很难理解。」（8372–8374）
- 「而另一方面，把类和方法分解开也是毫无意义的，这会使客户更复杂，迫使客户对象去理解各个小部分是如何组合在一起的。更糟的是，有的概念可能会完全丢失。铀原子的一半并不是铀。而且，粒度的大小并不是唯一要考虑的问题，我们还要考虑粒度是在哪种场合下使用的。」（8375–8377）
- 「菜谱式的规则是没有用的。但大部分领城都深深隐含着某种逻辑一致性，否则它们就形不成领域了。这并不是说领域就是绝对一致的，而且人们讨论领域的方式肯定也不一样。但是领域中一定存在着某种十分复杂的原理，否则建模也就失去了意义。」（8378–8381）——OCR「领城」应为「领域」
- 「通过反复重构最终会实现柔性设计，以上就是其中的一个原因。随着代码不断适合新理解的概念或需求，CONCEPTUAL CONTOUR（概念轮廓）也就逐渐形成了。」（8384–8385）
- 「（从单个方法的设计，到类和MODULE的设计，再到大比例结构的设计（参见第16章），高内聚低耦合这一对基本原则都起着重要的作用。这两条原则既适用于代码，也适用于概念。为了避免机械化地遵循它，我们必须经常根据我们对领域的直观认识来考虑它的基本问题，并以此来调整技术思路。在做每个决定时，都要问自己：“这是根据当前模型和代码中的一组特定关系做出的权宜之计呢，还是反映了底层领域的某种轮廓？”）」（8386–8390）

### 10-16 §10.4 续：WHOLE VALUE、模式陈述与重构信号｜PDF203–204｜行8391–8422
- 「寻找在概念上有意义的功能单元，这样可以使得设计既灵活又易懂。例如，如果领域中对两个对象的“相加”（addition）是一个连贯的整体操作，那么就可以把它作为整体来实现。不要把add（）拆分成两个步骤。」（8391–8393）
- 「从稍大的范围来看，每个对象都应该是一个独立的、完整的概念，也就是一个“WHOLE VALUE”（整体值）。」（8393–8394）——脚注：「Ward Cunningham在［Cunningham 1995］中介绍了WHOLE VALUE。」（8398）
- 「出于同样的原因，在任何领域中，都有一些细节是用户不感兴趣的。前面假想的那个调漆应用程序的用户不会添加红色颜料或蓝色颜料，他们只是把已经做好的油漆拿来调，而油漆包含所有三种颜料。」（8395–8397）
- 「因此：把设计元素（操作、接口、类和AGGREGATE）分解为内聚的单元，在这个过程中，你对领域中一切重要划分的直观认识也要考虑在内。在连续的重构过程中观察发生变化和保证稳定的规律性，并寻找能够解释这些变化模式的底层CONCEPTUAL CONTOUR。使模型与领域中那些一致的方面（正是这些方面使得领域成为一个有用的知识体系）相匹配。」（8409–8413）
- 「我们的目标是得到一组可以在逻辑上组合起来的简单接口，使我们可以用UBIQUITOUS LANGUAGE把它们表述出来，并且使那些无关的选项不会分散我们的注意力，也不增加维护负扭。」（8414–8415）——OCR「负扭」应为「负担」
- 「设计即使是按照CONCEPTUAL CONTOUR进行，也仍然需要修改和重构。当连续的重构往往只是做出一些局部修改（而不是对模型的概念产生大范围的影响）时，这就是模型已经与领域相吻合的信号。如果遇到了一个需求，它要求我们必须大幅度地修改对象和方法的划分，那么这就是在向我们传递这样一条信息：我们对领域的理解还需要精化。」（8418–8421）

### 10-17 §10.4 示例：应计项目的 CONCEPTUAL CONTOUR（图10-11/10-12）｜PDF204–205｜行8423–8499
- 「在第9章中，基于对会计概念的更深层理解，我们对一个货款跟踪系统进行了重构。如图10-11所示。」（8425–8426）——OCR「货款」应为「贷款」
- 「新模型比原来的模型只多出一个对象，但职责的划分都发生了很大的变化。Schedule原来是在Calculator类中通过逻辑判断计算的，现在被分散到不同的类中，用于不同类型的手续费和利息计算。另一方面，手续费和利息的支付原来是分开的，现在也被合并到一起了。」（8427–8430）
- 「由于新发现的显式概念与领域非常吻合，而且Accrual Schedule的层次结构具有内聚性，因此开发人员认为这个模型更符合领域的CONCEPTUAL CONTOUR，如图10-12所示。新的Accrual Schedule的加入是开发人员早就预料到的，因为有一些需求早已等待它来处理了。这样，她选择的模型除了使现有功能更清晰、简单之外，还很容易引入新的Schedule。」（8431–8434）
- 图10-11（8440–8483，重构前的原模型）：Fee Calculator（monthlyAmount、dayOfMonthDue、calculateFeesForDate（））、Interest Calculator（rate、freq、dateOffset、accountingPeriodStartDate、interestDueAmount、calculatelnterestForDate（））、两类 Payment History、Asset（principalAmount、lastAccrualCalculationDate、calculateInterestForDate（）、calculateFeesForDate（）、calculateAccrualsThrough（Date））、Accrual Schedule（ledgerName、accrualsForDateRange（））、Payment（date、amount、ledgerName）——OCR 残缺：「Fec Calculator」「Interes Calculator」「calculatelnterestForDate」「JledgerName」等为 OCR 误识，未据以补全
- 图10-12（8484–8499）：Accrual Schedule（ledgerName、accrualsForDateRange（））为基类，子类 Daily Compound Interest（rate）与 Monthly Fee（amount、dayOfMonthDue）——OCR「DatcRange」应为「DateRange」；注：「新的Accrual Schedule只需重写accrualsForDatcRange（）方法即可。」（8494–8496）
- 「但是，她是否找到了一个CONCEPTUAL CONTOUR，使得领域设计可以随着应用程序和业务的演变而改变和发展呢？我们无法确定一个设计如何处理意料之外的改变，但她认为她的设计中一些不合适的地方已经有所改进了。」（8435–8437）

### 10-18 §10.4 示例（续）：一个未预料到的改变（图10-13）与原因｜PDF205–206｜行8500–8528
- 「一个未预料到的改变。随着项目向前进展，又出现了一个新的需求——需要制定一些详细的规则来处理提早付款和延迟付款。这位开发人员在研究问题的时候，很高兴地发现利息付款和手续费付款实际上使用相同的规则。这意味着新的模型元素可以很自然地使用Payment类。」（8500–8511，跨页断行已拼接）
- 图10-13（8512–8524）：Asset 与 Payment，新增 Early Payment Policy（evaluate（Payment））参与判断——OCR「cvaluate」应为「evaluate」，图内文字部分残缺
- 「原有的设计导致两个Payment History类之间必然出现重复（这个难题可能使得开发人员认识到Payment类应该被共享，这样就会从另外一条途径得到类似的模型）。新元素之所以很容易就添加进来了，并不是因为她预料到了这个改变，也不是因为她的设计灵活到了足以容纳任何可能修改的程度。真正的原因是经过前面的重构，设计能够很好地与领域的基本概念产生吻合了。」（8525–8528）

### 10-19 §10.4 收尾：四个模式的协同与「概念过载」｜PDF206｜行8529–8535
- 「INTENTION-REVEALING INTERFACE使客户能够把对象表示为有意义的单元，而不仅仅是一些机制。SIDE-EFFECT-FREE FUNCTION和ASSERTION使我们可以安全地使用这些单元，并对它们进行复杂的组合。CONCEPTUAL CONTOUR的出现使模型的各个部分变得更稳定，也使得这些单元更直观，更易于使用和组合。」（8530–8533）
- 「然而，我们仍然会遇到“概念过载”（conceptual overload）的问题——当模型中的互相依赖性过多时，我们就必须把大量问题放在一起考虑。」（8534–8535）

### 10-20 §10.5 模式：STANDALONE CLASS——互相依赖性与思考负担｜PDF207｜行8536–8570
- 「互相依赖性使模型和设计变得难以理解、测试和维护。而且，互相依赖性很容易越积越多。」（8538）
- 「当然，每个关联都是一种依赖性，要想理解一一个类，必须理解它与哪些对象有联系。与这个类有联系的其他对象还会与更多的对象发生联系，而这些联系也是必须要弄清楚的。每个方法的每个参数的类型也是一个依赖性，每个返回值也都是一个依赖性。」（8539–8541）——OCR「一一个」应为「一个」
- 「MODULE和AGGREGATE的目的都是为了限制互相依赖的关系网。当我们识别出一个高度内聚的子领域并把它提取到一个MODULE中的时候，一组对象也随之与系统的其他部分解除了联系，这样就把互相联系的概念的数量控制在一个有限的范围之内。」（8550–8552）
- 「即使是在MODULE内部，设计也会随着依赖关系的增加而变得越来越难以理解。这加重了我们的思考负担，从而限制了开发人员能处理的设计复杂度。隐式概念比显式的引用增加的负担更大。」（8555–8557）
- 「我们可以将模型一直精炼下去，直到每个剩下的概念关系都表示出概念的基本含义止。在一个重要的子集中，依赖关系的个数可以减小到零，这样就得到一个完全孤立的类，它只有很少的几个基本类型和基础库概念。」（8558–8560）——OCR「含义止」应为「含义为止」
- 「隐式概念，无论是否已被识别出来，都与显式引用一样会加重思考负担。虽然我们通常可以忽略像整数和字符串这样的基本类型值，但无法忽略它们所表示的意义。例如，在第一个调漆应用程序的例子中，Paint对象包含三个公共的整数，分别表示红、黄、蓝三种颜色值。Pigment Color对象的创建并没有增加所涉及的概念数量，也没有增加依赖关系。但它确实使现有概念更明显、更易于理解了。另一方面，Collection的size（）操作返回一个整数（只是一个简单的合计数），它只表示整数的基本含义，因此并不产生隐式的新概念。」（8565–8570）

### 10-21 §10.5 续：质疑依赖、模式陈述与调漆示例；引出闭合操作｜PDF207–208｜行8571–8600
- 「我们应该对每个依赖关系提出质疑，直到证实它确实表示对象的基本概念为止。这个仔细检查依赖关系的过程从提取模型概念本身开始。然后需要注意每个独立的关联和操作。仔细选择模型和设计能够大幅减少依赖关系——常常能减少到零。」（8571–8573）
- 「低耦合是对象设计的一个基本要素。尽一切可能保持低耦合。把其他所有无关概念提取到对象之外。这样类就变成完全孤立的了，这就使得我们可以单独地研究和理解它。」（8574–8576）
- 「当一个类与它所在的模块中的其他类存在依赖关系时，比它与模块外部的类有依赖关系要好得多。同样，当两个对象具有自然的紧密耦合关系时，这两个对象共同涉及的多个操作实际上能够把它们的关系本质明确地表示出来。我们的目标不是消除所有依赖，而是消除所有不重要的依赖。」（8577–8580）
- 「尽力把最复杂的计算提取到STANDALONE CLASS（孤立的类）中，可能实现此目的的一种方法是把具有紧密联系的类中所含有的VALUE OBJECIT建模出来。」（8590–8591）——OCR「OBJECIT」应为「OBJECT」
- 「从根本上讲，油漆的概念与颜色的概念紧密相关。但在考虑颜色（甚至是颜料）的时候却与不必去考虑油漆。通过把这两个概念变为显式概念并精炼它们的关系，所得到的单向关联就可以表达出重要的信息，同时我们可以对Pigment Color类（大部分计算复杂性都隐藏在这个类中）进行独立的分析和测试。」（8592–8595）——OCR「却与不必」应为「却不必」
- 「低耦合是减少概念过载的最基本办法。孤立的类是低耦合的极致。消除依赖性并不是说要武断地把模型中的一切都简化为基本类型，这样只会削弱模型的表达能力。本章要讨论的最后一个模式CLOSURE OF OPERATION（闭合操作）就是一种在减小依赖性的同时保持丰富接口的技术。」（8597–8600）

### 10-22 §10.6 模式：CLOSURE OF OPERATION——数学闭合、模式陈述与VALUE OBJECT偏好｜PDF208–209｜行8601–8641
- 「两个实数相乘，结果仍为实数（实数是所有有理数和所有无理数的集合）。由于这一点永远是正确的，因此我们说实数的“乘法运算是闭合的”：乘法运算的结果永远无法脱离实数这个集合。当我们对集合中的任意两个元素组合时，结果仍在这个集合中，这就叫做闭合操作。」（8603–8605）——引注「-—The Math Forum, Drexel Universily」（8606）——OCR「Universily」应为「University」
- 「当然，依赖是必然存在的，当依赖性是概念的一个基本属性时，它就不是坏事。如果把接口精简到只处理一些基本类型，那么它也就没有什么表达能力了。但我们也经常为接口引人很多不必要的依赖性，甚至是整个不必要的概念。大部分引起我们兴趣的对象所产生的行为仅用基本类型是无法描述的。」（8607–8610）——OCR「引人」应为「引入」
- 「另一种常见的对设计进行精化的方法就是我所说的CLOSURE OF OPERATION（闭合操作）。这个名字来源于最精炼的概念体系，即数学。1+1=2。加法运算是实数集中的闭合运算。……例如，XSLT的基本用法是把一个XMIL文档转换为另一个XML文档。这种XSLT操作就是XML.文档集合中的闭合操作。闭合的性质极大地简化了对操作的理解，而且闭合操作的链接或组合也很容易理解。」（8611–8617）——OCR「XMIL」应为「XML」、「XML.」应为「XML」
- 模式陈述：「在适当的情况下，在定义操作时让它的返回类型与其参数的类型相同。如果实现者（implementer）的状态在计算中会被用到，那么实现者实际上就是操作的一个参数，因此参数和返回值应该与实现者有相同的类型。这样的操作就是在该类型的实例集合中的闭合操作。闭合操作提供了一个高层接口，同时又不会引入对其他概念的任何依赖性。」（8618–8626，跨页断行已拼接）
- 「这种模式更常用于VALUE OBJECT的操作。由于ENTITY的生命周期在领域中十分重要，因此我们不能为了解决某一向题而草率创建一个ENTITY。……但是，ENTITY通常不会成为计算结果。因此，大部分闭合操作都应该到VALUE OBJECT中去寻找。」（8627–8631）——OCR「向题」应为「问题」
- 「半个闭合操作」：「参数类型与实现者的类型一致，但返回类型不同；或者返回类型与接收者（receiver）的类型相同但参数类型不同。这些操作都不是闭合操作，但它们确实具有CLOSURE OF OPERATION的某些优点。当没有形成闭合操作的那个多出来的类型是基本类型或基础库类时，它几乎与CLOSURE OF OPERATION一样减轻了我们的思考负担。」（8634–8638）

### 10-23 §10.6 示例：从集合中选择子集（Java Iterator vs Smalltalk select）｜PDF209–210｜行8642–8677
- 代码转述（行8646–8656）：Java 版以 Iterator 遍历 employees 集合，以 anEmployee.salary()<40000 为条件，将匹配元素加入 new HashSet() 的 lowPaidEmployees——OCR「1owPaidEmployees」应为「lowPaidEmployees」、「i£」应为「if」，代码标点全角化、排版散乱（OCR 残缺）
- 「从概念上讲，上段代码只是从集合中选择了一个子集。是否真的有必要使用Iterator这个额外的概念以及它所带来的所有机制上的复杂性呢？如果是使用Smalltalk，我将在Collection上调用“select”操作，把测试作为一个参数传递给它。返回值将是一个新的Collection，其中只包含通过测试的那些元素。」（8657–8660）
- 代码转述（行8661、8670–8672，跨页断行已拼接）：Smalltalk 版 lowPaidEmployees := employees select: [:anEmployee | anEmployee salary < 40000]——OCR「anBmployee」应为「anEmployee」；行8662–8664（1268/10/269）为页码噪声
- 「Smalltalk的Collection还提供了其他一些这样的函数，它们返回派生的Collection（可能是几种不同的具体类）。这些操作并不是闭合操作，因为它们把一个block（块）作为参数。但block在Smalltalk中是一个基础库类型，因此它们并不会增加开发人员的思考负担。由于返回值与实现者的类型相匹配，因此它们可以像一系列过滤器一样被串接在一起，使读写代码都变得很容易。它们并没有引人与选择子集无关的外来概念。」（8673–8677）——OCR「引人」应为「引入」

### 10-24 本章收束：柔性设计的总体风格与团队技巧要求｜PDF210｜行8678–8686
- 「本章介绍的模式演示了一个总体的设计风格和一种思考设计的方式。把软件设计得便于、容易预测且富有表达力，可以有效地发挥抽象和封装的作用。我们可以对模型进行分解，使得对象更易于理解和使用，同时仍具有功能丰富的、高级的接口。」（8679–8681）
- 「运用这些技术需要掌握相当高级的设计技巧，甚至有时编写客户端代码也需要掌握高级技巧才能运用这些技术。MODEL-DRIVEN DESIGN的作用受细节设计的质量和实现决策的质量影响很大，而且只要有少数几个开发人员没有弄清楚它们，整个项目就会偏离目标。」（8682–8684）
- 「尽管如此，团队只要愿意培养这些建模和设计技巧，那么按照这些模式的思考方式就能够开发出可以反复重构的软件，从而最终创建出非常复杂的软件。」（8685–8686）
- （行8678「米米*」为章节小结分隔符的 OCR 噪声）

### 10-25 §10.7 声明式设计——动机、可执行规格、两大缺陷与适用边界｜PDF210–211｜行8687–8723
- 「使用ASSERTION可以得到更好的设计，虽然我们只是用一些相对非正式的方式来检查这些ASSERTON。」（8688–8689）——OCR「ASSERTON」应为「ASSERTION」
- 「以上这些正是采用声明式设计的部分动机。声明式设计对于不同的人来说具有不同的意义，但通常是指一种编程方式—把程序或程序的一部分写成一种可执行的规格（specification）。使用声明式设计时，软件实际上是由一些非常精确的属性描述来控制的。声明式设计有多种实现方式，例如，可以通过反射机制来实现，或在编译时通过代码生成来实现（根据声明来自动生成传统代码）。这种方法使其他开发人员能够根据字面意义来使用声明。它是一种绝对的保证。」（8696–8700）
- 「口声明式语言并不足以表达一切所需的东西，它把软件束缚在一个由自动部分构成的框架之内，使软件很难扩展到这个框架之外。口 代码生成技术破坏了迭代循环，它把生成的代码合并到手写的代码中，使得重新生成的破坏作用变得很大。」（8707–8710）——「口」为项目符号"■"的 OCR 噪声
- 「尽管基于规则的程序原则上是声明式的，但大多数系统都有一些用于性能优化的“控制谓词”（control predicate）。这种控制代码引入了副作用，这样行为就不再完全由声明式规则来控制了。添加、删除规则或重新排序可能导致预料不到的错误结果。」（8715–8718）
- 「据我所知，声明式设计的最大价值是用一个范围非常窄的框架来自动处理设计中某个特别单调且易出错的方面，例如持久化和对象关系映射。最好的声明式设计能够使开发人员不必去做那些单调乏味的工作，同时又完全不限制他们的设计自由。」（8721–8723）

### 10-26 侧栏：特定于领域的语言——与UBIQUITOUS LANGUAGE的结合及其缺陷｜PDF211–212｜行8724–8754
- 「特定于领域的语言是一种有趣的方法，它有时也是一种声明式语言。采用这种编码风格时，客户代码是用一种专门为特殊领域的特殊模型定制的语言而编写的。例如，运输系统的语言可能包括cargo（货物）和route（路线）这样的术语，以及一些用于组合这些术语的语法。然后，程序通常会被编译成一种传统的面向对象的语言，由一个类库为这些术语提供实现。」（8725–8728）
- 「在这样的语言中，程序可以具有极强的表达能力，并且与UBIQUITOUS LANGUAGE之间形成最紧密的结合。特定于领域的语言是一个令人振奋的概念，但在我所见过的基于面向对象技术的方法中，这种语言也存在自身的缺陷。」（8729–8731）
- 「为了精化模型，开发人员需要修改语言。这可能涉及修改语法声明和其他语言解释功能，以及修改底层的类库。虽然我完全赞同“高级技术和设计概念是学来的”这个观点，但我们必须冷静地评估特定团队当前的技术水平，以及将来的维护团队可能的技术水平。此外，用同一种语言实现的应用程序和模型之间是“无缝”的，这一点很有价值。另一个缺点是当模型被修改时，很难对客户代码进行重构，使之与修改之后的模型及与其相关的特定于领域的语言保持一致。」（8732–8737）
- 「有一种不同的范式——Scheme编程语言，能够比对象更好地实现特定于领域的语言。在Schere编程语言中（它是“函数式编程”家族的一个代表），有些部分非常类似于标准的编程风格，因此既具有特定于领域的语言的表达能力，又不会造成系统的分裂。」（8747–8750，跨行破折号已拼接）——OCR「Schere」应为「Scheme」
- 「这种技术可能在非常成熟的模型中能够发挥出最大的作用，在这样的模型中，客户代码可能是由另一个不同的团队编写的。通常，这样的设置会导致产生一种有害的结果——团队被分成两部分，框架由那些技术水平较高的人来构建，而应用程序则由那些技术水平较差的人来构建了，但也并不是非得如此。」（8751–8754）

### 10-27 §10.8 声明式设计风格：三模式齐备即具备条件；引出SPECIFICATION扩展｜PDF212｜行8755–8766
- 「一旦你的设计中有了INTENTION-REVEALING INTERFACE、 SIDE-EFFECT-FREE FUNCTION 和ASSERTION，那么你就具备了使用声明式设计的条件。当我们有了可以组合在一起来表达意义的元素，并且刻画了效果（或根本没有明显效果）之后，就可以获得声明式设计的很多益处了。」（8757–8759）
- 「柔性设计使得客户代码可以使用声明式的设计风格。为了说明这一点，下一节将会把本章介绍的一些模式结合起来使用，从而使SPECIFICATION更灵活，更符合声明式设计的风格。」（8760–8761）
- 「第9章介绍了SPECIFICATION的基本概念、它在程序中扮演的角色，以及它在实现中的意义。现在，让我们来看看几个额外的、有吸引力的技巧，它们在规则很复杂的情况下可能非常有用。」（8763–8764）
- 「SPECIFICATION 是由“谓词”（predicate）这个众所周知的形式化概念变来的。谓词还有其他一些有用的特性，我们可以对这些特性进行有选择的利用。」（8765–8766）

### 10-28 §10.8 使用逻辑运算对SPECIFICATION进行组合——and/or/not闭合操作与容器示例｜PDF212–214｜行8767–8832
- 「当使用SPECIFICATION时，我们很容易就会遇到需要把它们组合起来使用的情况。正如我们刚刚提到的那样，SPECIFICATION是谓词的一个例子，而谓词可以用“AND”“OR”和 “NOT” 等运算进行组合和修改。这些逻辑运算都是谓词这个类别之下的闭合操作，因此SPECIPICATION组合也是CLOSURE OF OPERATION。」（8768–8772）——OCR「SPECIPICATION」应为「SPECIFICATION」
- 「随着SPECIFICATION的通用性逐渐提高，创建一个可用于各种类型的SPECIFICATION的抽象类或接口会变得很有用。这需要把参数类型定义为某种高级的抽象类。」（8773–8774）
- 代码转述（行8775–8776、8784–8794，跨页断行已拼接）：public interface Specification { boolean isSatisfiedBy(Object candidate); }；ContainerSpecification 实现中先以卫语句（guard clause）判断 if (!(candidate instanceof Container)) return false（8777–8778 说明「这个抽象要求在方法的开始处放置一条卫语句（guard clause），但是没有卫语句也不影响它的功能」）——OCR「1£」「retuzn」「ObJect」等多处错讹（OCR 残缺）
- 代码转述（行8795–8801）：扩展 Specification 接口，加入 Specification and(Specification other)、Specification or(Specification other)、Specification not() 三个新操作——OCR「加人」应为「加入」
- 代码与示例转述（行8802–8826）：Specification ventilated = new ContainerSpecification(VENTILATED); Specification armored = new ContainerSpecification(ARMORED); Specification both = ventilated.and(armored)；多种通风容器时 Specification either = ventilatedType1.or(ventilatedType2)；Specification cheap = (ventilated.not()).and(armored.not()) 以「指定一种没有特殊性质的"便宜的"容器来禁止把砂存放在特殊容器中」——OCR「ventilatedrypel/ventilatedrype2」应为「ventilatedType1/ventilatedType2」
- 「从简单元素构建复杂规格的能力提高了代码的表达能力。以上组合是以声明式的风格编写的。」（8828–8829）、「由于SPECIFICATION实现的方法存在不同，提供这些运算符的难易程度也不同。下面是一个非常简单的实现，在有些情况下它的效率很差，而有些情况下则很实用。举这个例子只是为了起到说明的作用。像任何模式一样，它也有很多实现方式。」（8830–8832）

### 10-29 图10-14 与组合实现代码：AbstractSpecification、And/Or/Not Specification｜PDF214–216｜行8833–8900
- 图10-14 转述（行8833–8850）：「图10-14 SPECIFICATION的COMPOSITE（组合）设计」——类图中 Composite Specification 一处标注 COMPOSITE（［Gamma et al. 1995］），操作为 isSatisfied(Object)：boolean、and(Specification)：Specification、or(Specjfication)：Specification、no(Specification)：Specification；图中另标注 DECORATOR（［Gamma et al. 1995］）；子类为 LeafSpecification、OR Specification、AND Specification、NOT Specification——OCR 图形符号散乱（--0、2、2、1 等为噪声，OCR 残缺）；「no（Specification）」应为「not（Specification）」
- 代码转述（行8851–8888，跨页断行已拼接）：public abstract class AbstractSpecification implements Specification，其 and/or/not 分别 return new AndSpecification(this, other)、new OrSpecification(this, other)、new NotSpecification(this)；public class AndSpecification / OrSpecification extends AbstractSpecification 各持有 Specification one 与 Specification other，构造器赋值后 isSatisfiedBy 分别以 && 与 || 连接 one.isSatisfiedBy(candidate) 与 other.isSatisfiedBy(candidate)——OCR「publ.ic」「issatisfiedBy」等大小写错讹（OCR 残缺）
- 代码转述（行8892–8900）：public class NotSpecification extends AbstractSpecification 持有 Specification wrapped，isSatisfiedBy 返回 !wrapped.isSatisfiedBy(candidate)——OCR「xi」「Yi」应为「x;」「y;」之类

### 10-30 简单实现的取舍与第2章回顾：按需添加特性｜PDF215–216｜行8901–8917
- 「为了便于阅读，上面这段代码写得尽可能简单。如前所述，它在有些情况下是低效的。可能会有一些其他的实现选择，使得对象的数目减至最少，或极大地提高速度，或者与某个项目的特定技术兼容。重要的是模型捕捉到领域的关键概念，同时有一个忠实于该模型的实现。这就为解决性能问题预留了很大的空间。」（8901–8903、8910，跨页断行已拼接）
- 「此外，这些完全的通用性在很多情况下并不需要。特别是AND可能比其他运算用得更多，而且它的实现的复杂程度也较小。如果你只需要AND，那么完全可以只实现它，这没有什么可担心的。」（8911–8913）
- 「我们回顾一下第2章的示例中的对话，开发人员显然没有实现他们SPECIFICATION中的“satisfied by”行为。在他们进行那段讨论的时候，SPECIFICATION只是“根据需要来构建”（building to order）。尽管如此，抽象仍然完整，而且功能添加起来也相对简单。使用模式并不意味着构建你不需要的特性。它们可以过后再添加，只要不引起概念混淆即可。」（8914–8917）

### 10-31 示例：COMPOSITE SPECIFICATION的另一种实现（栈/数组编码，对象粒度教训）｜PDF216–217｜行8918–8949
- 「有些实现环境不能使用粒度很小的对象。我曾经遇到过一个项目，它有一个对象数据库，这个数据库为每个对象分配一个ID并跟踪这个ID。每个对象都占有很大的内存空间，并且产生很大的性能开销，因此总的地址空间成为一个限制因素。我在领域设计中的一些重要地方使用了SPECIFICATION，当时我认这是一个很好的决定。但我使用了一个过于细致的实现（像本章中描述的那样），这无疑是个错误。它产生了数百万个粒度非常小的对象，使整个系统的速度变得非常缓慢。」（8920–8925）——OCR「我认」应为「我认为」
- 「下面的例子给出了一种替代实现，它把组合SPECIFICATION编码为一个字符串或者数组（这个数组对逻辑表达式进行了编码），然后在运行时进行解析。」（8926–8927）、「（即使你没明白它的实现也不要紧，重要的是认识到用逻辑运算符来实现SPECIFICATION的方式有很多。如果最简单的方法不适用于你的情况，可以选择其他的方法。）」（8928–8929）
- 栈结构转述（行8930–8936）：「“Cheap Container”的SPECIFICATION栈的内容」自栈顶向下依次为 AndSpecificationOperator（FLY WEIGHT）、NotSpecificationOperator（FLY WEIGHT）、Armored、NotSpecificationOperator、Ventilated——OCR「FLY WEIGHT」应为「FLYWEIGHT」
- 「当我们想测试一种候选方案时，必须解释这个结构，这可以通过把每个元素弹出来并计算它（或者是根据运算符的需要弹出下一个元素）来实现。最后将得到如下结果：and （not （armored）， not （ventilated））」（8937–8939）
- 「这种设计有一些优点（+）和缺点（-）」：+ 对象个数较少；+ 内存使用效率高；- 需要更高级的开发人员（8940–8943）；「你必须根据自己的实际情况做出权衡，找到一种适合你的实现。基于相同的模式和模型可以创建出完全不同的实现。」（8948–8949）

### 10-32 包含（subsumption）：动机——化学品规格变严的列表需求｜PDF217｜行8950–8979
- 「最后要讲的这个包含特性并不是经常需要，而且实现起来也很难，但有时它确实能够解决很困难的问题。它还能够表达出一个SPECIFICATION的含义。」（8951–8952）
- 「再次考虑一下前面的化学仓库打包程序的例子。每个Chemical都有一个Container Specification，而且 Packer SERVICE确保当把Drum分配到Container中时，所有这些Container Specification都被满足，一切都没有问题••••直到有人改变了规则。」（8953–8955）——「••••」为省略号 OCR 噪声
- 「每隔几个月都会发布一组新的规则，我们的用户希望能够生成一个列表，把那些已经有了更严格要求的化学品列出来。」（8956–8957）
- 「但用户要求的是把所有那些存放要求变得更严格的化学品都列出来。或许仓库里目前还没有这样的化学品，或者它们碰巧被装到了一个更严格的容器中。无论是哪种情况，刚才的那个报告都不会列出它们。」（8961–8963）
- 「我们引入一个用于直接比较两种SPECIFICATION的新操作。boolean subsumes (Specification other);」「更严格的SPECIFICATTON包含不太严格的SPECIFICATION。用更严格的SPECIFICATION来取代不严格的SPECIFICATION不会遗漏掉先前的任何需求。如图10-15所示。」（8964–8968）——OCR「SPECIFICATTON」应为「SPECIFICATION」
- 图10-15 转述（行8969–8979）：「汽油容器的SPECIFICATION变严格了」——new 的 Container Specification 为「ventilated AND armored」，对 old 的 Container Specification「ventilated」调用 subsumes(old) 返回 true；反之对 new 调用 subsumes(new) 为 false——OCR「ncw」应为「new」、「糸〇」等为噪声（OCR 残缺）

### 10-33 包含=逻辑蕴涵：A→B 与 MinimumAgeSpecification 示例｜PDF217–218｜行8987–9007
- 「在SPECIFICATION语言中，我们说新的SPECIFICATION 包含旧的SPECIFICATTON，因为任何满足新SPECIFICATION的对象都将满是旧SPECIFICATION。」（8987–8988）——OCR「满是」应为「满足」、「SPECIFICATTON」应为「SPECIFICATION」
- 「如果把每个SPECIFICATION看成一个谓词，那么包含就等于逻辑蕴涵（logical implication）。使用传统的符号，A一B表示声明A蕴涵声明B，因此，如果A为真，则B也为真。」（8989–8990）——OCR「A一B」应为「A→B」
- 「让我们把这个逻辑应用于我们的容器匹配需求。当一个SPECIFICATION被修改时，我们想知道新SPECIFICATION是否满足旧SPECIFICATION的所有条件。New Spec - Old Spec。也就是说，如果新规格为真，那么旧规格一定也为真。要证明一般情况下的逻辑蕴涵是很难的，但特殊情况就很容易证明。例如，特殊的参数化的SPBCIFICATION可以定义它们自己的包含规则。」（8991–8995）——OCR「SPBCIFICATION」应为「SPECIFICATION」、「New Spec - Old Spec」应为「New Spec → Old Spec」
- 代码转述（行8996–9003）：public class MinimumAgeSpecification 持有 int threshold；isSatisfiedBy(Person candidate) 返回 candidate.getAge() >= threshold；subsumes(MinimumAgeSpecification other) 返回 threshold >= other.getThreshold()
- 代码转述（行9004–9007）：JUnit 测试片段——drivingAge = new MinimumAgeSpecification(16)、votingAge = new MinimumAgeSpecification(18)，断言 assertTrue(votingAge.subsumes(drivingAge))

### 10-34 AND 特例：Composite Specification 的 subsumes 实现与亚里士多德侧栏｜PDF218–219｜行9008–9055
- 「还有一个有用的特例适用于解决Container Specification问题，它就是用单一的逻辑操作AND把SPECIFICATION接口与包含结合起来。」（9008–9009）
- 「AAND B-A。或者在更复杂的情况中，AAND B AND C- AANDB」（9015–9017）——OCR「AAND B-A」应为「A AND B → A」、「AAND B AND C- AANDB」应为「A AND B AND C → A AND B」
- 「这样，如果Composite Specification能够把所有由“AND”连接起来的叶子（Ieaf） SPECIFICATION收集到一起，那么我们要做的事情只是检查包含规格（subsuming SPECIFICATION）是否含有被包含规格（subsumed specification）的所有叶子——这些叶子的集合是被包含规格的所有叶子的集合的超集。」（9018–9026，跨页断行已拼接）——OCR「Ieaf」应为「leaf」
- 代码转述（行9010–9014）：public interface Specification 含 boolean isSatisfiedBy(Object candidate)、Specification and(Specification other)、boolean subsumes(Specification other)；代码转述（行9027–9041）：CompositeSpecification 的 subsumes(other)——若 other instanceof CompositeSpecification，则取 other.leafSpecifications() 逐一检查 this.leafSpecifications().contains(...)，任一不含返回 false；否则直接检查 leafSpecifications().contains(other)；全部通过返回 true
- 「遗憾的是，当把OR和NOT也包括进来时，这些证明会变得更复杂。在大多数情况下，最好避免出现这样的复杂性：要么选择放弃一些运算符，要么不使用包含。如果这二者同时需要，那么要慎重考虑这样做的价值是否多过它所带来的麻烦。」（9043–9045）
- 侧栏转述（行9046–9055）：「受SPECIFICATION约束的亚里士多德」——Specification manSpec = new ManSpecification()、mortalSpec = new MortalSpecification()；assert manSpec.subsumes(mortalSpec)；Man aristotle = new Man()；assert manSpec.isSatisfiedBy(aristotle)；assert mortalSpec.isSatisfiedBy(aristotle)；配三段论：「所有人都是要死的／亚里士多德是一个人／因此，亚里士多德会死」

### 10-35 10.9 切入问题的角度：总起｜PDF219｜行9056–9061
- 「本章展示了一系列技术，它们用于澄清代码意图，使得使用代码的后果变得显而易见，并且解除模型元素的耦合。尽管有这些技术，但要想实现这样的设计还是很难的。我们不能只是看着一个庞大的系统说：“让我们把它设计得灵活点吧。”我们必须选择具体的目标。下面介绍几种主要方法，然后给出一个扩展的示例，它显示了如何把这些模型结合起来使用，并用于处理更大的设计。」（9057–9061）

### 10-36 10.9.1 分割子领域｜PDF219–220｜行9062–9079
- 「我们无法一下子就能处理好整个设计，而需要一步一步地进行。我们从系统的某些方面可以看出适合用哪种方法处理，那么就把它们提取出来加以处理。如果模型的某个部分可以被看作是专门的数学，那么可以把这部分分离出来。如果应用程序实施了某些用来限制状态改变的复杂规则，那么可以把这部分提取到一个单独的模型中，或者提取到一个允许声明规则的简单框架中。」（9063–9074，跨页断行已拼接；其中 9064–9066「28］／10／282」为书页页脚噪声，未收录）
- 「随着这些步骤的进行，不仅新模型更整洁了，而且剩下的部分也更小、更清晰了。在剩下的模型中，有的部分是用声明式的风格来编写的——这些可能是根据专门数学或验证框架编写的声明，或者是子领域所采用的任何形式。」（9075–9077）
- 「重点突击某个部分，使设计的一个部分真正变得灵活起来，这比分散精力泛泛地处理整个系统要有用得多。第15章将更深入地讨论如何选择和管理子领域。」（9078–9079）

### 10-37 10.9.2 尽可能利用已有的形式｜PDF220｜行9080–9090
- 「我们不能把从头创建一个严密的概念框架当作一项日常的工作来做。在项目的生命周期中，我们有时会发现并精炼出这样一个框架。但更常见的情况是，可以对你的领域或其他领域中那些建立已久的概念系统加以修改和利用，其中有些系统已经被精化和提炼达几个世纪之久。例如，很多商业应用程序涉及会计学。会计学定义了一组成熟的ENTTTY和规则，我们很容易对这些ENTITY和规则进行调整，得到一个深层的模型和柔性设计。」（9081–9085）——OCR「ENTTTY」应为「ENTITY」
- 「有很多这样的正式概念框架，而我个人最喜欢的框架是数学。数学的强大功能令人惊奇，它可以用基本数学概念把一些复杂的问题提取出来。很多领域都涉及数学，我们要寻找这样的部分，并把它挖掘出来。专门的数学很整齐，可以通过清晰的规则进行组合，并且很容易理解。下面我要举一个例子，用它来结束本章，它来自我过去的经历——它就是“股份数学”（Shares Math）。」（9086–9090）

### 10-38 示例：把各种模型结合起来使用——股份数学（最初的付款分配设计）｜PDF220–221｜行9091–9146
- 「第8章讲述了在银团贷款系统项目上发生的一次模型突破的故事。现在我们将更详细地讨论这个例子，这里我们只集中讨论设计的一个特性，并与原来项目上的特性进行比较。」（9093–9094）
- 「该应用程序的一个需求是，当借款者偿付本金时，默认是根据放贷方的股份来分配这笔钱。」（9095）
- 图10-16 转述（行9098–9105）：「最初的付款分配设计」——Loan 以［owner］关联 Share；Loan 操作 distributePrincipalPayment(Money): Map 与 getAmount(): Money；Share 属性 owner: Company、amount: Money
- 代码转述（行9110–9146，跨页断行已拼接）：public class Loan 持有 Map shares；distributePrincipalPayment(double paymentAmount) 遍历 loanShares.keySet()，按 initialLoanShareAmount / total * paymentAmount 计算每股偿还额 paymentShareAmount，构造 Share 放入 paymentShares，并将 loanShares 中该 owner 的份额更新为 initialLoanShareAmount - paymentShareAmount 后返回 paymentShares；getAmount() 遍历所有 Share 累加返回 total——OCR「distributerrincipalPayment」应为「distributePrincipalPayment」、「getshareAmount」应为「getShareAmount」等大小写错讹（OCR 残缺）

### 10-39 把命令和 SIDE-EFFECT-FREE FUNCTION 分开：拆分 distributePrincipalPayment｜PDF221–222｜行9147–9196
- 「这个设计已经有了INTENTION-REVEALING INTERFACE。但distributePaymentPrincipal（）方法做了一件很危险的事情。它计算要分配的股份，并且还修改了Loan。我们通过重构把查询从修改操作中分离出来。」（9148–9153，跨页断行已拼接）——OCR「distributePaymentPrincipal（）」应为「distributePrincipalPayment（）」（与行9113的方法名一致）；9147 行首「廢」与行尾「毅」为侧栏标题的 OCR 噪声
- 图10-17 转述（行9155–9164）：Loan：calculatePrincipalPaymentShares(Money): Map、applyPrincipalPaymentShares(Map)、getAmount()；Share：owner: Company、amount: Money
- 代码转述（行9165–9192）：applyPrincipalPaymentShares(Map paymentShares) 遍历 paymentShares.keySet()，将 loanShare 更新为 loanShare.getAmount() - paymentShare.getAmount()；calculatePrincipalPaymentShares(double paymentAmount) 遍历 loanShares，按 loanShare.getAmount() / total * paymentAmount 生成新的 Share 放入 paymentShares 返回——OCR「applyPrincipalPaymentghares」应为「applyPrincipalPaymentShares」、「HaghMap」应为「HashMap」、「1oanshare」应为「loanShare」等（OCR 残缺）
- 「客户代码现在如下：Map distribution = aLoan.calculatePrincipalPaymentshares（paymentAmount）；aLoan.applyPrincipalPaymentShares（distribution）；」（9193–9196）——OCR「calculatePrincipalPaymentshares」大小写错讹

### 10-40 把隐式概念变为显式概念：粒度过大问题与 Share Pie 的引入｜PDF222–223｜行9201–9239
- 「这段代码不算太差。FUNCTION把大量的复杂性封裝在INTENTION-REVEALING INTERFACE背后。但当我们添加applyDrawdown（），calculatereePaymentShares（）等一些函数之后，代码开始大量增加。每次扩充都使代码变得更复杂，速度也不断减慢。这可能是由于粒度过大造成的。传统的解决方法是把计算方法分解为子例程。这可能是一种不错的解决办法，但我们希望最终看到底层的概念边界，并深化模型。当设计元素具有这种CONCEPT-CONTOURING的粒度时，就可以把这些元素进行组合，得到所需的变体。」（9201–9206）——OCR「calculatereePaymentShares」应为「calculateFeePaymentShares」、「封裝」为「封装」繁混字
- 「现在我们有足够的条件来探索新模型了。在这个实现中，Share对象是被动的，它们是用一些复杂、低级的方式来操纵的。这是因为大部分与股份有关的规则和计算并不适用于单独的股份，而是用于成组的股份。有一个概念被漏掉了：股份互相之间是有关联的，同时部分又构成整体。如果能把这个概念显式地表达出来，就能更简洁地表示这些规则和计算。」（9208–9212，跨页断行已拼接）——9207 行首「8」为侧栏标题「把隐式概念变为显式概念」的 OCR 噪声
- 「Share Pie表示了一个特定的Loan的总体分布。它是一个ENTITY，其标识位于Loan AGGREGATE的内部。实际的分布计算可以被委托給Share Pie。」（9223–9224）——OCR「給」为「给」繁混字
- 图10-18 转述（行9213–9222）：「Share Pie的引入」——在 Loan 与 Share 之间插入 Share Pie，形成 Loan—Share Pie—Share（［owner］）的关联结构（OCR 残缺）
- 图10-19 转述（行9225–9239）：Loan：calculatePrincipalPaymentShares(double): Map、applyPrincipalPaymentShares(Map)、getAmount(): double；Share Pie：prorate(double): Map、increase(Map)、decrease(Map)、getAmount(): double；Share：owner: Company、amount: double

### 10-41 在进一步理解之后，把 Share Pie 变成一个 VALUE OBJECT｜PDF224–225｜行9245–9286
- 代码转述（行9245–9256）：public class Loan 持有 SharePie shares；calculatePrincipalPaymentDistribution(double paymentAmount) 直接 return getShares().prorated(paymentAmount)；applyPrincipalPayment(Map paymentShares) 调用 shares.decrease(paymentShares)——OCR「Sharerie」应为「SharePie」、「calculaterrincipalPaymentDistribution」应为「calculatePrincipalPaymentDistribution」（OCR 残缺）
- 「这样Loan就被简化了，而且Sharei算也被集中到了一个VALUE OBJECT中（这个VALUE OBJECT只负责这个计算）。但是，这个计算并没有真正变得通用和易用。」（9257–9258）——OCR「Sharei算」应为「Share 计算」
- 「这意味着不能再使用increase（Map）和decrease （Map）了，因为Share Pie必须是不变的。要更改Share Pie的值，必须替换整个Pie。因此需要使用addShares（Map）这样的方法来返回一个全新的、更大的Share Pie。」（9263–9265）
- 「让我们再进一步把它变成CLOSURE OF OPERATION。我们不采用“增加”Share Pie或向它添加Share，而只是把两个Share Pie加起来，结果是一个新的、更大的Share Pie。」（9266–9267）
- 「我们可以先把Share Pie上的prorate（）操作变成半个闭合操作，这只需要修改返回类型即可。我们把它重命名为prorated（），以便强调它没有副作用。“股份数学”开始成型了，最初它有4个操作。」（9268–9270）——9259 行尾「B」为侧栏标题「在进一步理解之后，把 Share Pie 变成一个 VALUE OBJECT」的 OCR 噪声
- 图10-20 转述（行9271–9286）：Loan：calculatePrincipalPaymentShares(double): Share Pie、applyPrincipalPaymentShares(Share Pie)、getAmount(): double；Share Pie：prorated(double): Share Pie、plus(Share Pie): Share Pie、minus(Share Pie): Share Pie、getAmount(): double；Share：owner: Company、amount: double

### 10-42 SharePie 实现：以 ASSERTION 注释的股份数学四操作｜PDF225–226｜行9291–9345
- 「我们可以为新的VALUE OBJECT Share Pie创建一些定义明确的ASSERTION。每个方法都有各自的意义。」（9291–9292）
- 代码转述（行9293–9341，跨页断行已拼接）：public class SharePie 持有 Map shares；getAmount() 遍历 shares 累加返回 total；minus(SharePie otherShares) 对两个 Pie 的 owners 并集逐一计算 getShareAmount(owner) - otherShares.getShareAmount(owner)，构造新 SharePie result 返回；plus(SharePie otherShares) 注明 similar to implementation of minus()；prorated(double amountToProrate) 以 getAmount() 为 basis，按 share.getAmount() / basis * amountToProrate 构造新 SharePie proration 返回——OCR「sharerie/Sharerie」应为「SharePie」、「addA11」应为「addAll」等（OCR 残缺）
- 「总股份等于各股份之和」（9304，getAmount 的 ASSERTION 注释）
- 「两个Pie之差等于这两个股东所持胶份之差」（9320–9321，minus 的 ASSERTION 注释）——OCR「胶份」应为「股份」
- 「两个Pie的组合就等于把这两个股东所精股份加到一起」（9326–9328，plus 的 ASSERTION 注释）——OCR「精股份」应为「持股份」
- 「总额可以依照所有股东所占的股份按比例划分」（9339–9340，prorated 的 ASSERTION 注释）

### 10-43 新设计的柔性（侧栏）：Loan 简化与声明式的支取/偏差计算｜PDF226–227｜行9346–9384
- 「现在，最重要的Loan类中的方法已经很简单了，如下：」（9347，侧栏标题「新设计的柔性」——行9346 OCR「器新设计的柔性鹽」含噪声字「器」「鹽」）
- 代码转述（行9348–9357）：public class Loan 持有 SharePie shares；calculatePrincipalPaymentDistribution(double paymentAmount) 直接 return getShares().prorated(paymentAmount)；applyPrincipalPayment(SharePie paymentShares) 调用 setShares(shares.minus(paymentShares))——OCR「PaymentAmount」大小写错讹（OCR 残缺）
- 「这些简短的方法中的每一个都表达了其自己的含义。本金偿付表示从货款中按照股份减去偿付额。对已偿付的本金进行分配是指在股份持有者之间按比例分配。Share Pie的设计使我们能够在Loan代码中使用声明式风格，所编写的代码读起来像是业务交易的概念定义，而不像是一种计算。」（9358–9360）——OCR「货款」应为「贷款」
- 「现在，其他交易类型（由于过于复杂没有在前面列出）也很容易声明了。例如，货款支取是根据贷方的Facility股份来分配的。新支取的数额被加到未偿货款（Loan）中。用我们的新领域语言可以描述如下：」（9361–9363）——OCR「货款」应为「贷款」
- 代码转述（行9364–9374）：Facility 持有 SharePie shares，calculateDrawdownDefaultDistribution(double drawdownAmount) 直接 return getShares().prorated(drawdownAmount)；Loan.applyDrawdown(SharePie drawdownShares) 调用 setShares(shares.plus(drawdownShares))——OCR「calculateprawdownDefaultDistribution」应为「calculateDrawdownDefaultDistribution」、「arawdowrn/arawdown」应为「drawdown」、「ShareBie」应为「SharePie」（OCR 残缺）
- 代码转述（行9379–9384）：查看每个贷方原定贷款额与实际贷款额之差——SharePie originalAgreement = aFacility.getShares().prorated(aLoan.getAmount())；SharePie actual = aLoan.getShares()；SharePie deviation = actual.minus(originalAgreement)

### 10-44 Share Pie 设计特性清单与「熟悉的形式」｜PDF227｜行9385–9405
- 「Share Pie设计的一些特性使这种组合变得很容易，也提高了代码的表达能力。」（9385）
- 「口 复杂的逻辑通过SIDE-EFFECT-FREE FUNCTION被封装到了专门的VALUE OBJECT中。大部分复杂逻辑都已经被封装到这些不变的对象中。由于Share Pie是VALUE OBJECT，因此数学运算可以创建新实例，我们可以用这些新实例来替换旧实例。」「Share Pie的所有方法都不会修改任何现有对象。这使我们在中间计算中能够自由地使用Plus（）、minus（）和pro-rated（），并通过组合它们来实现预期效果，同时又不会产生其他副作用。我们还可以根据这些方法来创建分析特性（以前，只有在执行实际计算的时候才能调用这些方法，因为在每次调用之后数据就改变了）。」（9386–9392）——行首「口」为项目符号 OCR 噪声
- 「口修改状态的操作很简单，而且是用ASSERTION来描述的。利用“股份数学”的高层抽象，我们可以用声明式的风格来精确地编写交易的固定规则。例如，差值是实际股份减去根据Facility 的Share Pie按比例分配的Loan额。」（9393–9395，跨页断行已拼接）——行首「口」为项目符号 OCR 噪声
- 「模型概念解除了耦合，操作只涉及最少的其他类型。Share Pie上的一些方法显示出它们是CLOSURE OF OPERATION（加、减方法是Share Pie之下的闭合操作）。其他操作以简单的总额作为参数或返回值，它们虽然不是闭合操作，但只增加了极少的概念负担。Share Pie只与一个其他的类—Share有密切交互。这样，Share Pie就非常直截了当，易于理解和测试，也很容易通过组合来产生声明式的交易。这些特性都是从数学形式中继承得来的。」（9396–9400）
- 「熟悉的形式使我们更容易掌握协议（protocol）。最初用于操作股份的协议本来也是可以用财务术语来设计的，而且从原则上讲，这样的设计也能很灵活。但它有两个缺点。首先，我们必须从头开始设计它，这是一项困难且没有把握完成的任务。其次，每个处理它的人都必须先学会它。而我们现在这种设计的好处是，看到股份数学的人会发现他们对这个早已十分熟悉了，而且由于设计与算术规则保持严格一致，因此人们不会被误导。」（9401–9405）

### 10-45 本章结论｜PDF227｜行9406–9411
- 「把与数学形式有关的那部分向题提取出来之后，我们得到了一个柔性的Share设计，这使得我们可以进一步精炼核心的Loan和Facility方法（参见第15章有关CORE DOMAI的讨论）。」（9406–9407）——OCR「向题」应为「问题」、「CORE DOMAI」应为「CORE DOMAIN」
- 「柔性设计可以极大地提升软件处理变更和复杂性的能力。正如本章的例子所示，柔性设计在很大程度上取决于详细的建模和设计决策。柔性设计的影响可能远远超越某个特定的建模和设计问题。第15章将讨论柔性设计的战略价值，我们将把它作为一种工具，用来精炼领域模型，以便使大型和复杂的项目更易于掌握。」（9408–9411）

## 第11章 分析模式的应用（OCR 9416–9947，PDF 228–238）

### 11-1 章开篇：借鉴已记载的模式经验｜PDF228｜行9416–9435

- 「一位经验丰富的开发人员在研究领域问题时，如果发现了他所熟悉的某种职责或某个关系网，他会想起以前这个问题是如何解决的。以前尝试过哪些模型？哪些是有效的？在实现中有哪些难题？它们是如何解决的？先前经历过的尝试和失败会突然间与新的情况联系起来。这些模式当中有一些已经记载到文献中供大家分享，这样我们就可以借鉴这些积累的经验。」（9420–9423）
- 「与第二部分提出的基本构造块模式和第10章介绍的柔性设计原则相比，这些模式属于更高级和专用的模式，其中还使用了少量对象来表示某种概念。利用这些模式，可以避免一些代价高昂的尝试和失败过程，而直接从一个已经具有良好表达力和易实现的模型开始工作，而且构造块模式已经解决了一些可能很难学习的微妙的问题。我们可以从这样一个起点来重构和试验。然而，它们并不是现成的解决方案。」（9424–9428）
- 「在《分析模式》一书中，Martin Fowler这样定义分析模式（［Fowler 1997, p.8］）：分析模式是一种概念集合，用来表示业务建模中的常见构造。它可能只与一个领域有关，也可能跨越多个领域。」（9429–9431）
- 「Fowler所提出的分析模式来自于实践经验，因此只要用在适当的情况下，它们会非常实用。」（9432）
- 「“分析模式”这个名字本身就强调了其概念本质。分析模式并不是技术解决方案，而只是用来指导人们设计特定领域中的模型。」（9433–9435）

### 11-2 分析模式的实现价值与 Fowler 的过账规则引文｜PDF228–229｜行9436–9457

- 「但从这个名字中我们看不出分析模式也讨论了大量实现问题，包括—-些代码。Fowler知道，在不考虑实际设计的情况下进行单纯的分析是有缺陷的。」（9436–9437）——OCR『—-些』应为『一些』。
- 「当构建一个新的［会计］实务时，我们会创建一个新的过账规则（posting rule）的实例网。这项工作完全不需要重新编译或重建系统，而且不影响系统的运行。有时我们将不可避免地需要过账规则的某个新的子类型，但这种情况并不多见。」（9440–9442）
- 「在一个成熟的项目上，模型选择往往是根据实用经验做出的。人们已经尝试了各种组件的多种实现方法。其中的一些实现已经被采用，甚至已经到了维护阶段。这些经验可以帮助人们避开很多问题。分析模式的最大作用是借鉴其他项目的经验，把那些项目中所做的广泛的设计方向讨论和实现结果的经验与当前的模型结合起来。脱离设计模式的上下文来讨论模型思想将使它们很难应用，而且还会产生分析与设计脱节的风险，而这一点正是MODEL-DRIVEN DESIGN坚决反对的。」（9447–9452）
- 「用实例比用单纯的抽象描述能够更好地解释分析模式的原则和应用。本章将举出两个例子，它们选自［Fowler 1997］中的“Inventory and Accounting”（库存与账户）一章，在这两个例子中开发人员使用一个小型的、有代表性的模型。本章只是 了讲解这两个例子而概述分析模式。」（9453–9455）——OCR『只是 了』应为『只是为了』。
- 「本章的重点是说明如何将它们集成到领域驱动的设计过程中。」（9457）

### 11-3 示例 账户的利息计算：背景与初始类图｜PDF229｜行9458–9492

- 「第10章显示了开发人员为某种专用会计应用程序去寻找更深层模型的各种可能途径。而本示例则是另外一个场景，这里开发人员将深入挖掘Fowler的《分析模式》一书，从中寻找有用的思想。」（9460–9462）
- 「来复习一下。用于跟踪货款和其他有息资产的应用程序将计算所产生的利息和手续费，并跟踪借方的付款情况。夜间会有一个批处理操作提取这些数字，并传递给原来的会计系统，并标明每个账目应该过账到哪个分类账中。这种设计虽然能工作，但使用起来却很麻烦，修改起来也很复杂，而且不易于交流沟通。」（9463–9466）
- （图11-1 初始的类图，行9467–9486，OCR 残缺：含 Interest Calculator、Fee Calculator、Asset、Fee Payment History、Interest Payment History 等类；属性含 monthlyAmount、dayOfMonthDue、rate、freq、dateOffset、accountingPeriodStartDate、interestDueAmount 等；方法名如 calculateInterestForDate() 被 OCR 误读为 calculatelnterestForDate()；类与成员的对应关系被展平）
- 「开发人员决定读一下《分析模式》的第6章 “Inventory and Accounting” 最与之相关的内容。下面是摘录的一些」（9487–9489）

### 11-4 《分析模式》中的账户模型：Account/Entry 与复式记账｜PDF230｜行9497–9534

- 「所有种类的业务应用程序都需要对账户进行跟踪，因为账户中保存了与数值有关的信息（通常是钱）。在很多应用程序中，仅跟踪账户总额是不够的，记录和控制账户总额的每次修改也很重要。这也是会计模型最基本的动机。」（9498–9500）
- （图11-2 一个基本的账户模型，行9501–9509，OCR 残缺：Account（balance: Quantity）关联多个 Entry（amount/whenCharged/whenBooked），约束 balance = sum(entries.amount) 被 OCR 误读为「（balance = sum（enuriesamomml）」；图11-3 一个交易模型，行9515–9526，OCR 残缺：引入 Transaction（..2）关联 Account 与 Entry，约束 ｛sum（entries.amount）=0｝）
- 「通过插入一个Entry（项）可以向账户中添加数值，而插人一个负的Entry则可以从账户中删除数值。Entry永远不会被删除，因此整个历史就会被保留下来。余额就是把所有Entry加到一起所得到的结果。这个余额可以实时计算，也可以被缓存，这是由Account接口封装的一个实现决策。」（9510–9512）——OCR『插人』应为『插入』。
- 「会计的一条基本原则就是账目的平恒。钱不会无中生有，也不会无故消失。它只能从一个账户转移到另一个账户。」（9513–9514）——OCR『平恒』应为『平衡』。
- 「这就是众所周知的“复式记账”（doublc-entry book-keeping）概念。每个贷方都有与之相应的借方。当然，像其他守恒定律一样，它只适用于一个封闭的系统，这个系统包含了入账和出账的所有明细。但很多简单的应用程序并不需要这么严格。」（9527–9529）——OCR『doublc-entry』应为『double-entry』。
- 「开发人员（开发人员1）通过阅读这些内容获得了一些新的思路。她把这章内容介绍给她的同事（开发人员2）看，这位同事正在与她一起编写一些利息计算逻辑，而且他还编写了夜间批处理程序。他们一起对模型作了一些粗略的修改，并在模型中加进了一些在阅读该章时看到的模型元素。」（9531–9534）

### 11-5 图11-4 新提出的模型与专家对话｜PDF231｜行9537–9591

- （图11-4 新提出的模型，行9537–9567，OCR 残缺：Interest Calculator 向 Interest Account 插入新 Entry、Fee Calculator 向 Fee Account 插入新 Entry；Transaction 关联 due 与 payment 两类 Entry，其约束 ｛sum(entries.amount)=0｝ 被 OCR 误读）
- 「开发人员1：利用这个新模型，我们可以在Interest Account中为每笔利息收入增加一个Entry，而不是只调整interestDueAmount。然后，另一个付款的Entry会使其平账。」（9569–9570）
- 「开发人员2：我不确定这里使用“Transaction”（交易）是否完全正确。定义讲的是把钱从一个Account转移到另一个Account，而不是两个Entry在同一个Account中互相平衡。」（9572–9573）
- 「专家：为什么要把应计项目和付款联系在一起呢？它们在会计系统中分开过帐的。Account的平账才是主要的。沿着一个一个的Entry，我们就可以查出所有的账目。」（9580–9581）——OCR『过帐』应为『过账』。
- 「专家：当然可以。应计项目 （accrual）是指在一笔支出或收入发生的时候把它记录到账目中，而永远不管现金实际是何时过帐的。因此，利息每天都会计算，但只有在（举例来说）月末才会支付。」（9587–9588）——OCR『过帐』应为『过账』。

### 11-6 图11-5/图11-6：分开应计与付款、去掉 Transaction 的基于账户模型｜PDF232｜行9596–9654

- 「开发人员1：是的，我们确实需要这个词。好，现在这个图怎么样？」（9596）
- （图11-5 还是原来的类图，只是把应计项目和付款分开了，行9597–9617，OCR 残缺：Interest Calculator 增加的成员名 OCR 误读严重（行9609–9611 等）；图11-6 基于账户的图，里面没有Transaction，行9623–9649，OCR 残缺：方法 calculateAccruedInterestForDate()/calculateAccruedFeesForDate() 被 OCR 误读，Interest Calculator/Fee Calculator 分别向 Interest Account/Fee Account 插入 Entry，Entry 分为 due/payment）
- 「开发人员1：现在，我们可以删掉与付款有关的所有复杂计算了，而且我们引入了“accrual”这个术语，它更好地表明了我们的意图。」（9618–9619）
- 「专家：那么我们就不会有Account对象了吧？我本来还希望能够把应计项目、付款和余额等项目都放到这个对象中呢。」（9620–9621）
- 「专家：这看起来确实好极了！」「开发人员2：批处理脚本也只需要简单的修改就能使用这些新对象。」（9650–9651）
- 「开发人员1：新的Interest Calculator过几天才能使用。有好几个测试需要修改一下。但修改之后测试会更清楚。」（9652–9653）

### 11-7 重构精化：Entry 子类 Payment/Accrual 与实现折中｜PDF233｜行9658–9724

- 「两位开发人员开始基于新模型进行重构。他们在着手编写代码并加强设计时，又有了一些对模型进行精化的新想法。」（9658–9659）
- 「通过更仔细的研究，他们发现这两个子类在应用程序中的职责稍有不同，而且都是非常重要的领域概念，于是决定为Entry创建两个子类：Payment和Accrual。但另一方面，从“Entry是从何而来的”这个角度来看，那么无论它是因为手续费而产生的，还是因为利息产生的，在概念和行为上都没有任何区别。它们只是出现在适当的Account中。」（9660–9663）
- 「但遗憾的是，开发人员们发现，出于实现方面的考虑，他们不得不放弃最后这一次抽象。数据存储在关系表中，而且项目标准要求在不运行程序的情况下也能解释清楚这些表。这意味着要把手续费项和利息项分开保存到不同的表中。根据他们所使用的对象-关系映射框架，将手续费项和利息项保存到不同表中的唯一方法就是创建具体的子类 （Fee Payment、 Interest Payment等等）。如果换成另外一种基础设施，他们或许还可以避免使用这些笨拙的子类。」（9664–9668）
- 「我在这个大部分是虚构的故事中讲述这段小插曲的原因是想说明我们在现实中总是会遇到这类小的障碍。我们必须做出一些适当的折中选择然后继续前进，而不能因为这些小问题而改变MODEL-DRIVEN DESIGN的方向。」（9669–9671）
- （图11-7 实现之后的类图，行9672–9722，OCR 残缺：Interest Calculator 与 Fee Calculator 各有 accrualFor(Date): Entry 类方法（OCR 误读为 aCcrual fgr/ACcruaIFpg），并标注 SIDE-EFFECT-FREE FUNCTION，含前置条件「在这个日期（Date），Entry尚不存在」（行9694–9695）与后置条件「；在既表示某个日期（Date）的手续费也表示该日期利息的Account中，Entry存在」（行9696–9699，OCR『；』应为『:』）；Asset 有 accrualsFor(Date): Set/insertAccrualsForDate(Date)；Entry 子类化为 Payment 与 Accrual，再具体化为 Fee Payment、Interest Payment（OCR 误读 Paymcnt）、Fee Accrual、Interest Accrual，并注明创建这些子类是由于在实现中做了一些折中选择、此项目所使用的对象-关系映射框架导致不得不做出这些折中（行9709–9712））
- 「新的设计更易于分析和测试，因为最复杂的功能已被封装到了SIDE-EFFECT-FREE FUNCTION中。剩下的命令的代码很简单（因为它只需调用各种FUNCTION），并使用了ASSERTION。」（9723–9724）

### 11-8 盲点发现与示例引入：对夜间批处理程序的深入理解｜PDF233–234｜行9725–9741

- 「有时，我们甚至想象不到，程序的一些部分也能从领域模型获益。它们可能从简单开始，并一步步机械地演变。它们看上去就像是复杂的应用程序代码，而不是领域逻辑。分析模式在找到这些盲点方面特别有用。」（9725、9732–9733，跨页断行已拼接）
- 「在下一个例子中，一位开发人员对夜间批处理程序的内部机制产生了新的想法，以前他并没有从领域的角度来考虑这一问题。」（9734–9735）
- 「几星期后，改进后的基于Account的模型基本完成了。像往常一样，虽然新设计更加清晰了，但它又暴露了其他一些问题。开发人员（开发人员2）在修改夜间批处理程序以使之与新设计交互的时候，发现批处理程序的行为与《分析模式》一书中所讲的一些概念有联系。」（9738–9740）

### 11-9 过账规则器与三种触发模式｜PDF234–235｜行9742–9782

- 「会计系统经常提供同一个基本财务信息的多种视图。一个账户可能用于跟踪收人，而另一个账户可能用于跟踪该收人的估税。如果我们希望系统自动更新估税总额，那么这两个账户的实现将会彼此紧密关联。在有些系统中，大部分账目都是由这些规则而产生的，在这样的系统中，依赖逻辑会变得一团糟。即使是在规模不大的系统中，这样的交叉过账也会很复杂。减少这种缠杂不清的依赖性的第一步是通过引入一个新的对象来使这些规则明朗化。」（9743–9747）——OCR『收人』应为『收入』。
- （图11-8 基本过账规则的类图，行9748–9758，OCR 残缺：Account 经 input/output 关联 Posting Rule，Posting Rule 经 calculation 关联 Method，图中另有孤立标记 B01）
- 「当过账规则的input账目收到一个新的Entry时，这个Entry就会触发过账规则。然后过账规则会生成一个新的Entry（基于其自己的计算方法），并将这个Entry插入到其 “output” 账目中。在工资系统中，工资Account中的Entry可能会触发一个过账规则，此规则计算30%的估计收入所得税，并将其作为一个Entry插人到扣税Account中。」（9759–9762）——OCR『插人』应为『插入』。
- 「（1） “主动触发”（Eager firing）是最明显的选择，但通常也是最不实用的。每当一个Entry被插入到Account中时，它立即就触发过账规则，并立即进行所有更新。」（9771–9772）
- 「（2） “基于Account的触发”允许推迟处理。在过后的某个时刻，向Account发送一条消息，令其触发过账规则，来处理自从上一次触发以来所插人的所有Entry。」（9773–9774）——OCR『插人』应为『插入』。「（3）最后，“基于过账规则的触发”由外部代理来启动，它通知过账规则触发。过账规则负责查找自从上次触发以来插人到其输入的Account中的所有Entry。」（9775–9776）——OCR『插人』应为『插入』。
- 「将这三种触发模式添加到UBIQUITOUS LANGUAGE中对于成功使用这种模式具有至关重要的意义，这与模型对象定义本身同等重要。」（9779–9780）

### 11-10 对话：Posting Service FACADE 与触发模式、Method 的去除｜PDF235–236｜行9783–9854
- 「开发人员2：有的时候，夜间批处理程序成为了一个隐藏问题的地方。脚本的行为中隐含了领域逻辑，而且正在变得越来越复杂。很长时间以来，我一直想用MODEL-DRIVEN DESIGN的方法来修改一下批处理，将领域层分离出来，并使脚本本身成为领域层之上的一个简单的层。但我一直没有想出这个领域模型应该是什么样的。看上去它似乎只是一些操作步骤，而把它们实现为对象没什么实际意义。我读完《分析模式》一-书中有关Posting Rule的内容后，获得了一些思路。这个图就是我所想到的［递过来一张草图］。」（9785–9790）——OCR『一-书』应为『一书』。
- （图11-9 在批处理中使用过账规则的一个思路，行9793–9814，OCR 残缺：batch script（OCR 误读 batch scvipt）execute 调用 Posting Service（post（amount, ledgerName）），Posting Rule 关联 Metnod（OCR 误读 Method）与 ledgemlame（OCR 误读 ledgerName），Entry 子类 Fee Payment、Interest Payment（OCR 误读 Paywent）、Fee Accrual、Interest Accrual（OCR 误读 Iuterest）各带 method）
- 「开发人员1:Posting Service是指什么？／开发人员2：这是个FACADE，它提供了会计应用程序的API，并且将其呈现为一个SERVICE。实际上我使用它已经有一段时间了，主要用来筒化批处理代码，而且它也为我提供了一个INTENTION-REVEALING INTERFACE，可用于向老系统过账。」（9821–9824）——OCR『筒化』应为『简化』。
- 「开发人员1：很有趣，那么你打算为这些Posting Rule（过账规则）使用哪种触发模式？／开发人员2：我还没有想那么多。／开发人员1：“主动触发”可能适用于Accrual，因为批处理程序实际上通知Asset插入Accrual，但“主动触发”可能不适用于Payment，因为Payment是在白天输入的。」（9825–9828）
- 「开发人员1：虽然我讨厌过分挑剔，但我确实认为Method的使用不正确。我认为在概念上Method是用于计算要过账的总额的，比方说，在收入上计算20%的扣税。但我们的情形很简单：它始终是过账的全额。我想Posting Rule本身应该是知道要过账给哪个Account的，这个Account对应于我们的ledger name（分类账名称）。」（9842–9845）
- 「开发人员2：哦，那么如果让Posting Rule负责查知正确的ledger name，我们可能就完全不鸦要Method了。实际上，选择正确的ledger name这件事情变得越来越复杂了。它已经是收入类型（手续费或利息）与“Asset类别”（公司对每种Asset所使用的分类）的组合了。我希望新模型能够在解决这个复杂性上有所帮助。／开发人员1：好的，我们就把重点集中在这里。Posting Rule负责根据Account的属性来选择Ledger。」（9846–9852）——OCR『不鸦要』应为『不需要』。

### 11-11 重构结果：图11-10/11-11 与 SINGLETON 折中｜PDF237–238｜行9858–9924
- 「在接下来的几天时间里，这两位开发人员设计出了一个模型，并对代码进行了重构，使得批处理程序只是简单地依次访问各个Asset，并向每个Asset发送几条非常浅显易懂的消息，然后提交数据库事务。复杂性被转移到领域层中，领域层中的对象模型使问题变得更加明确，也更抽象。」（9860–9862）
- （图11-10 含有过账规则的类图，行9863–9887，OCR 残缺：Asset（amount、assetClass、insertAccrualsForDate（Date）、firePostingRules（）、fees、interest）持有 Posting Rule（fee rule、interest rule，标注「识别Asset的属性」）与 Posting Service（post（amount, ledgerName, g…）及 process（Account）），Posting Rule 经 Map（assetClass --> ledgerName）协作，Account 有 balance/lastPostingDate/postNewEntries（Posting Rule），Entry 有 amount/date）
- （图11-11 显示了规则触发的序列图，行9888–9907，OCR 残缺：script 依次调用 Asset 的 insertAccrualsFor（date）与 firePostingRules（），Asset 调 fees/interest 的 postNewEntries（feeRule, assetClass），Account.postEntry（entry, assetClass）经 Map.get（assetClass）得 ledgerName（OCR 误读 ledgerNamc）后调 Posting Service.post（amount, ledgerName, …），并注明 and repeat for interest Account）
- 「在一些细节问题上，这两位开发人员开发的模型与《分析模式》中给出的相差甚远，但他们认为二者在概念本质上还是相同的。有一个问题令他们稍感不安，那就是在Posting Rule的选择中把Asset牵扯进来了，因为Asset知道每个Account的性质（手续费或利息），而且它也是脚本的自然访问点。」（9908–9909、9917，跨页断行已拼接）
- 「在规则对象直接与Account 发生关联的情况下，这些对象在每次实例化时（每次运行批处理程序时）都需要与Asset对象进行协作。可他们没有这样做，而是让Asset对象通过SINGLETON访问来查找这两个相关规则，并把相应的Account传递给它们。这样一来代码就变得更直接了，因此这是一个正确的决定。」（9918–9921）
- 「他们都感到从概念上看更好的做法是让Posting Rule只与Account发生关联，而令Asset只负责生成Accrual。他们希望等到有了后续的重构和更深入的理解之后再回头看这个问题，并找到一种将职责分离得更清楚而又不影响代码明确性的方法。」（9922–9924）

### 11-12 分析模式是很有价值的知识｜PDF238｜行9925–9947
- 「当你可以幸运地使用一种分析模式时，它一般并不会直接满足你的需求。但它为你的研究提供了有价值的指导，而且提供了明确抽象的词汇。它还可以指导我们的实现，从而省去很多麻烦。」（9926–9927）
- 「我们应该把所有分析模式的知识融入到知识消化和重构的过程中，从而形成更深刻的理解，并促进开发。当我们应用一种分析模式时，所得到的结果通常与该模式的文献中记载的形式非常相像，只是因具体情况不同而略有差异。但有时也完全看不出这个结果与分析模式本身有关，然而这个结果仍然是受该模式思想的启发而得到的。」（9928–9931）
- 「但有一个误区是应该避免的。当使用一个众所周知的分析模式中的术语时，一定要注意，不管其表面形式的变化有多大，都不要改变它所表示的基本概念。」（9932–9933）
- 「这样做有两个原因，一是模式中蕴含的基本概念将帮助我们避免问题，二是（也是更重要的原因）在UBIQUITOUS LANGUAGE中使用被广泛理解或至少是被明确解释的术语可以增强通用语言。如果在模型的自然演变过程中模型的定义也发生改变，那么就要修改模型名称了。」（9933–9936）
- 「很多对象模型都有文献资料可查，其中有些对象模型专门用于某个行业中的某种应用，而有些则是通用的模型。大部分对象模型都有助于开阔思路，但只有数少的一些模型精辟地阐述了选择这些模式的原理和使用的结果，而这些才是分析模式中最有用的部分。」（9937–9939）——OCR『数少』应为『少数』。
- 「这种对已组织好的知识的重复利用完全不同于通过框架或组件进行的代码重用，但是二者唯一的共同点是它们都提供了一种新思路的萌芽，而这种新思路先前可能并不十分明晰。一个模型，甚至一个通用框架，都是一个完整的整体，而分析则相当于一个工具包，它被应用于模型的一些部分。分析模式专注于一些最关键和最艰难的决策，并指明了各种替代和选择。它们提前预测了一些后期结果，而如果单靠我们自己去发现这些结果，可能会付出高昂的代价。」（9943–9947）

## 第12章 将设计模式应用于模型（OCR 9949–10344，PDF 239–248）

### 12-1 章开篇：设计模式与领域模式的区别｜PDF239｜行9954–9976
- 「至目前为止，本书中所探计的梭式都是专（针列如何在MOB DRINEN DBSIGN的上下文中解决领域模型中的问题。但实际上，大部分已发布的模式都更侧重于解决技术问题。设计模式与领域模式之间有什么区别？《设计模式》这部经典著作的作者为初学者指出了以下事实（［Gamma et al. 1995, p. 3］）：」（9954–9957）——OCR『探计』应为『探讨』；『梭式』应为『模式』；『专（针列』应为『专门针对』；『MOB DRINEN DBSIGN』应为『MODEL-DRIVEN DESIGN』。
- 「观点的不同会影响人们对什么是模式和什么不是模式的理解。一个人所认为的模式在另一个人看来可能是基本构造块。本书将在一定的抽象层次上讨论模式。设计模式并不是指像链表和散列表那样可以被封装到类中并供人们直接重用的设计，也不是直接用于整个应用程序或子系统的复杂的、专用于领域的设计。本书中的设计模式是对一些交互的对象和类的描述，我们通过定制这些对象和类来解决特定上下文中的一般设计问题。」（9958–9963）
- 「在《设计模式》介绍的模式中，有些（但并非所有）模式可用作领域模式，但在这样使用的时候，需要变换一下重点。《设计模式》一书中的设计模式把相关设计元素归为一类，这些元素能够解决在各种上下文中经常遇到的问题。这些模式的动机以及模式本身都是从纯技术角度描述的。但这些元素中的一部分在更广泛的领域和设计上下文中也适用，因为这些元素所对应的基本概念在很多领域中都会出现。」（9964–9968）
- 「除了《设计模式》一书中介绍的模式以外，近年来还出现了其他很多技术设计模式。有些模式反映了在一些领域中出现的深层次概念。这些模式都有很大的利用价值。为了在领域驱动的设计中充分利用这些模式，我们必须同时从两个角度看待它们：从代码的角度来看它们是技术设计模式，从模型的角度来看它们就是概念模式。」（9969–9972）
- 「我们将把《设计模式》所介绍的一个特定模式作为样例，来说明如何将人们所认为的设计模式应用到领域模型中，而且这个例子还将澄清技术设计模式与领域模式之间的区别。本章还将通过组合COMPOSITE（组合）和STRATEGY（策略）这两种模式演示如何通过改变思考方式，用一些经典的设计模式来解决领域问题。」（9973–9976）

### 12-2 模式：STRATEGY（也称为 POLICY）——GoF 模式卡片定义｜PDF240｜行9984–9998
- （GoF STRATEGY 结构图，行9987–9996，OCR 残缺：Context（contextinterfacel），OCR 误读 contextInterface()）关联 Strategy（algorithmfnterface()，OCR 误读 algorithmInterface()），后者派生 Concrete Strategy A（algorithmlnterface()）、Concrete Strategy B（algorithmInterface()）、Concrete StrategyC（algorithmInterface()），三个具体策略各带同名方法）
- 「定义了一组算法，将每个算法封装起来，并使它们可以互换。STRATEGY允许算法独立于使用它的客户而变化。（［Gamma et al. 1995］）」（9997–9998）

### 12-3 STRATEGY 的领域动机与「因此」方案｜PDF240–241｜行9999–10020
- 「领域模型包含一些并非用于解决技术问题的过程，将它们包含进来是因为它们对处理问题领域具有实际的价值。当必须从多个过程中进行选择时，选择的复杂性再加上多个过程本身的复杂性会使局面失去控制。」（9999–10001）
- 「当对过程进行建模时，我们经常会发现有不止一种合理的建模方式，而如果把所有的选择都写到过程的定义中，定义就会变得臃肿而复杂，而且我们所选择的行为描述也会因为混杂在其他行为中而显得模糊不清。」（10002–10004）
- 「我们希望把这些选择从过程的主体概念中分离出来，这样既能够看清主体概念，也能更清楚地看到这些选择。软件设计社区中众所周知的STRATEGY模式就是为了解决这个问题的，虽然它的侧重点在于技术方面。这里，我们把它当成模型中的一个概念来使用，并在该模型的代码实现中把它反映出来。我们同样也需要把过程中极易发生变化的部分与那些更稳定的部分分离开。」（10005–10009）
- 「因此：我们需要把过程中的易变部分提取到模型的一个单独的“策略”对象中。将规则与它所控制的行为区分开。按照STRATEGY设计模式来实现规则或可替换的过程。策略对象的多个版本表示了完成过程的不同方式。」（10010–10013）
- 「传统上，人们把STRATEGY模式看作-一种设计模式，这种观点的侧重点是它替换不同算法的能力。而把它看作领域模型的侧重点是其表示概念的能力，这里的概念通常是指过程或策略规则。」（10014、10019–10020，跨页断行已拼接）——OCR『看作-一种』应为『看作一种』。

### 12-4 示例：路线查找（Route-Finding）策略｜PDF241–242｜行10021–10104
- 「我们把一个Route Specification（路线规格）传递给Routing Service（路线服务），Routing Service的工作是构造一个满足SPECIFICATION的详细的Itinerary。这个SERVICE是一个优化引擎，可以通过调节它来查找最快的路线或最便宜的路线。」（10023–10026）
- （图12-1，行10027–10043，OCR 残缺）：Routing Service 带 findFastest（Specification）：ltincrary 与 findCheapest（Specification）：ltinerary 两个操作（OCR ltincrary/ltinerary 应为 Itinerary），creates→Itinerary，Itinerary ｛satisfied by｝Specification（行10031首「不」为 OCR 噪声）；Itinerary 关联 Leg（from:Location、departure:Date、to:Location、arrival:Date），Leg 关联 Voyage（dailyRate:Money，OCR 行10041「Vayage」应为「Voyage」）。图注：图12-1 带选项的SERVICE接口需要条件逻辑。
- 「这种设置看上去似乎没问题，但仔细观察路线代码就会发现，每个计算中都有条件判断，到处都是判断最快还是最便宜的逻辑。当为了做出更精细的航线选择而把新标准添加进来时，麻烦会更多。解决此问题的一种方法是把这些起调节作用的参数分离到STRATEGY中。这样它们就可以被明确地表示出来，并作为参数传递给Routing Service。现在，Routing Service就可以用一种完全相同的、无需进行条件判断的方式来处理所有请求了，它按照Leg Magnitude Policy（航段规模策略）的计算，找出一系列规模较小的Leg（航段）。」（10044–10051）
- 「这种设计具有《设计模式》中所介绍的STRATEGY模式的优点。按这种思路设计的应用程序可以提供丰富的功能，同时也很灵活，现在，可以通过安装适当的Leg Magnitude Policy来控制和扩展Routing Service的行为。图12-2中显示的只是最明显的两种STRATEGY（最快或最便宜）。可能还会有一些在速度和成本之间进行权衡考虑的组合策略。也可以加进其他的因素，例如在预订货物时优先选择公司自己的运输系统，而不是外包给其他运输公司。不使用STRATEGY模式同样能实现这些修改，但必须将逻辑添加到Routing Service的内部（这会是一个麻烦的过程），而且这些逻辑会使接口变得臃肿。解耦可以令Routing Service更清楚且易子测试。」（10052–10057、10087–10088，跨页断行已拼接）——OCR『易子』应为『易于』。
- （图12-2，行10062–10095，跨页，OCR 残缺）：顶部英文注释「The Routing Service chooses an Iinerary with a minimim total magniude ofthe Legs based on the chosen STRATECY.」（OCR：Iinerary→Itinerary、minimim→minimum、magniude→magnitude、ofthe→of the、STRATECY→STRATEGY）；类图：Leg（from:Location、departure:Date、to:Location、artival:Date；OCR artival→arrival）关联 Voyage（dailyRale:Money；OCR→dailyRate）；抽象类 Leg Magnilude Poficy（length（Leg）：double；OCR→Leg Magnitude Policy）派生 Leg Time Magnitudeo. 与 Leg Money Magnitude 两个子类（OCR Magnitudeo.→Magnitude），子类方法体 OCR 严重残缺：「lengrh（Leg leg）！/ return leg.elapsedTime（） * / leg.gerVoyage（l.gerDailyRated）：」与「lengihfLeg leg）/ retrn leg.elapsedTimep：」；次页 Routing Service 操作 find（Specification, Leg/ggnitdePoliey）：linerar（OCR→find（Specification, Leg Magnitude Policy）：Itinerary），creates→Itinerary，Itinerary ｛satisfiod by｝Specification（OCR satisfiod→satisfied）。图注：图12-2 通过STRATEGY（或者POLICY）选择确定的选项（STRATEGY是作为参数传入的）。
- 「现在，领域中的一个至关重要的规则明确地显示出来了，也就是在构建Iinerary时用于选择Leg的基本规则。它传达了这样一-个知识：路线选择的基础是航段的一个特定属性（有可能是派生属性），这个属性最后可归结为一个数字。这样，我们就可以在领域语言中用一句简单的话来定义Routing Service的行为：Routing Service根据所选定的STRATEGY来选择Lcg总规模最小的Itinerary。说明：以上讨论暗示了一件事。Routing Service在查找Itinerary时实际上会计算Leg的规模。这种方法在概念上比较直接，而且可以得到一个合理的原型实现，但它的低效率可能令人无法接受。第14章会再次讨论这个应用程序，其中将使用相同的接口，但具有完全不同的Routing Service实现。」（10096–10104）——OCR『Iinerary』应为『Itinerary』；『一-个』应为『一个』；『Lcg』应为『Leg』。

### 12-5 STRATEGY 对应实际业务策略：模式的另一层含义与GoF经验适用性（12.1节末讨论）｜PDF242–243｜行10105–10118
- 「我们在领域层中使用技术设计模式时，必须认识到这样做的另外一种动机，也是它的另一层含义。当所使用的STRATEGY对应于某种实际的业务策略时，模式就不再仅仅是一种有用的实现手段，而开始具有含义。」（10106–10108）
- 「技术了（但它在实现方面的价值井未改变）。」（10112）——OCR『井未』应为『并未』；此行为上句跨页延续，10108 行末与 10112 行首拼接后语义不完整，疑有 OCR 漏行，保留原文。
- 「设计模式的结论也完全适用于领域层。例如，在《设计模式》一书中，Gamma等人指出客户必须知道不同的STRATEGY，这也是一个建模关注点。如果单纯从实现上来考虑，使用策略可能会增加系统中对象的数目。如果这是一个问题，可以通过把STRATEGY实现为可在上下文中共享的无状态对象来减小开销。《设计模式》中对实现方法的全面讨论在这里也适用，这是因为我们仍然在使用STRATEGY，只是动机有些不同，这将影响我们的一些选择，但设计模式中的经验仍然是可以借鉴的。」（10113–10118）

### 12-6 模式：COMPOSITE——GoF 模式卡片定义｜PDF243｜行10119–10141
- （GoF COMPOSITE 结构图，行10122–10139，OCR 残缺）：Client 关联 Component；Component 带 operation（）（行10124缺右括号）、add（Component）、remove（Component）、gerChildfint（OCR 应为 getChild(int)），并以 children（1..*）自关联；Leaf 与 Composite 继承 Component：Leaf 带 Operation（）（OCR 大写 O），Composite 带 operation（）、for all children child.operation（）： 及 add（Component）、remove（Component）、getChild（int）；行10136「0-」为 OCR 噪声。
- 「将对象组织为树结构来表示部分-整体的层次结构。利用COMPOSITE，客户可以对单独的对象和对象组合进行同样的处理。（［Gamma et al. 1995］）」（10140–10141）

### 12-7 COMPOSITE 的领域动机与「因此」方案｜PDF243–244｜行10142–10168
- 「在对复杂的领域进行建模时，我们经常会遇到由多个部分组成的重要对象，这些部分本身又由其他一些部分组成，进而又由其他部分组成，有时甚至会出现任意深度的这种嵌套。在一些领域中，各个嵌套层在概念上是有区别的，但在另一些领域中，各个部分与它们所组成的整体是完全相同的事物，只是规模较小一些而已。」（10142–10145）
- 「当嵌套容器的关联性没有在模型中反映出来时，公共行为必然会在层次结构的每一层重复出现，而且嵌套也变得僵化（例如，容器通常不能包含同一层中的其他容器，而且嵌套的层数也是固定的）。客户必须通过不同的接口来处理层次结构中的不同层，尽管这些层可能在概念上没有区别。通过层次结构来递归地收集信息也变得非常复杂。」（10146–10149）
- 「当在领域中应用任何一种设计模式时，首先关注的问题应该是模式思想是否确实适合领域概念。以递归方式在一些相关对象中导航确实比较方便，但它们是否真的存在整体-部分层次结构？你是否发现可以通过某种抽象方式把所有部分都归到同一概念类型中？如果你确实发现了这种抽象方式，那么使用COMPOSTTE可以令模型的这些部分变得更清晰，同时使你能够深入细致地考虑设计模式的设计和实现问题。」（10150、10157–10160，跨页断行已拼接）——OCR『COMPOSTTE』应为『COMPOSITE』。
- 「因此：定义一个把COMPOSITE的所有成员都包含在内的抽象类型，在容器上实现一些用来查询信息的方法，这些方法可用来收集与容器内容有关的信息。“叶”节点基于它们自己的值来实现这些方法。客户只需使用抽象类型，而无需区分“叶”和容器。」（10161–10164）
- 「这相对来说是一种明显的结构层面上的模式，但设计人员通常不会主动地充实它的操作方面。COMPOSITE模式在每个结构层上都提供了相同的行为，而且.无论是较小的部分还是较大的部分，都可以对这些部分提出一些有意义的问题，这些问题能够透明地反映出它们的构成情况。这种严格的对称是组合模式具有强大能力的关键所在。」（10165–10168）——OCR『而且.无论是』应为『而且无论是』。

### 12-8 示例：由Route构成的Shipment Route｜PDF244–245｜行10169–10220
- 「完整的货物运输路线是很复杂的。首先，必须用卡车把集装箱运输到铁路终点站，然后运送到港口，然后用货轮运输到另一个港口，中间可能还会换船，最后还要进行地面运输才能到达目的地。」（10171–10173）
- 图12-3（行10174–10185，OCR 残缺）：插图标签：「货船运输」「航次A」「火车运输」「航次B」「由运输商ABC装货」「由运输商XYZ卸货」「由运输商XYZ装货」「停放在港口的LGB03位置」「leg1」「leg2」，行10181「316」为页码噪声；图注：「图12-3 由 “leg”（航段）构成的 “route”（航线）」（10185）。
- 「一个应用开发团队创建了一个对象模型，它表示了一个航线可以由任意多个航段组成。利用这个模型，开发人员可以根据预订请求来创建Route对象。他们可以把这些Leg组织为一步一步运输货物的操作计划。在这个过程中他们发现了一些问题。」（10186、10208–10209，两句间插图12-4，断行已拼接）
- 图12-4（行10191–10207，OCR 残缺）：类图元素：Route、Voyage、Leg（关联端标注「装货」「卸货」）、Transport Leg（属性 departureTime、arrivalTime，关联端标注「从」「到」）、Port Operation、Location，两处 ｛ordered｝ 与 V* 多重性标注（连线归属 OCR 定位残缺），行10190「223」为页码噪声；图注：「图12-4 Route的类图，其中Route由多个Leg组成」（10207）。
- 「开发人员原来一直认为航线是由任意多个航段组成的，而各个航段之间并没有什么区别。」「而事实上领域专家把航线看成是由5个逻辑段组成的一个序列。」（10210、10212，两句间为图12-5、图12-6）；图12-5（行10211，OCR 残缺）仅识别出图注「图12-5 开发人员的航线概念」，图内内容 OCR 未识别；图12-6（行10213–10217，OCR 残缺）图注「图12-6 业务专家的航线概念」，图内标签仅识别出「起」「出」「运」断片，行10216「12」为页码噪声。
- 「其他问题先不考虑，这些小段的航线可能是由不同的人在不同时间规划的，因此必须认识到它们之间是有区别的。通过更仔细的研究可以发现，“门航段”（doorleg）与其他航段大不相同，它涉及在当地雇用卡车甚至是客户运输，这与详细计划的铁路和货船运输完全不同。」（10218–10220，断行已拼接）——行10219句末「③17」为页码噪声（317），拼接时略去。

### 12-9 示例（续）：运用COMPOSITE统一航线结构｜PDF246–247｜行10226–10322
- 「反映了所有这些区别的对象模型渐渐变得复杂起来。」（10226）；图12-7（行10227–10249，OCR 残缺）：类图元素：Complete Route、Route Segment、Voyage（关联端标注「入港」「出港」）、Door Leg、Leg（关联端标注「装货」「卸货」）、Transport Leg（属性 departureTime、arrivalTime，关联端标注「从」「到」）、Port Operation、Location，多处 ｛ordered｝ 与 V* 多重性标注（行10238 OCR 作「（ordered｝」），行10233「3¢」为噪声；图注：「图12-7 详细的Route类图」（10249）。
- 「从结构上看这个模式并不是很差，但在操作计划的处理上失去了一致性，因此代码（甚至是行为的描述）变得复杂得多。其他复杂之处也渐渐显现。任何一条航线的遍历都涉及不同类型对象的多个集合。」（10250–10252，断行已拼接）
- 「运用COMPOSITE模式能使特定客户在不同层上都使用这种构造进行统一的处理，因为大的航线是由小段的航线构成的。这种视图在概念上也是合理的。每一层Route都是集装箱从一个地点到另一个地点的移动，最后就可以归结为一个独立的航段（参见图12-8）。」（10253–10255，断行已拼接）
- 图12-8（行10267–10303，OCR 残缺）：可识别元素：Composite Route（自关联，带 ｛ordered｝、* 多重性）、Route（操作 portOperationsO : Lislt——OCR 应为 portOperations() : List）、Door Leg、Voyage、Transport Leg（departureTime、arrivalTime；从、到）、Leg（装货 卸货）、Port Operation、Location、origin：、cutbound：（OCR 应为 outbound：）、山g／刘（OCR 残缺）、Loadl :Port Qperation／unloadl:Port Qperation（OCR 应为 Load1:Port Operation／unload1:Port Operation）；注释框文字：「任何在总体上适用于Route的操作，特别是那些遍历鏊个航线结构的操作」（10281–10283，OCR『鏊个』应为『整个』）；图注：「图12-8 使用COMPOSITE之后的类图」（10296、10303，图注跨图断开已拼接）。
- 「与前面那个类图不同，从现在这个静态类图看不出来门航段是如何与其他航段组合在一起的。但模型并不只包含静态类图。我们将通过其他的图（参见图12-9）和代码（现在代码简单多了）来表示这些航段的组合信息。这个模型抓住了所有这些不同类型的Route的深层关联性。生成操作计划的工作再次变得简单了，而且其他路线遍历操作也变得简单了。」（10256–10259，断行已拼接）
- 「利用这种“由航线组成航线”的方法，我们可以把各个航线的端点连接到一起来得到从一个地点到另一个地点的航线，从而可以实现各种不同的航线。我们可以把航线的一端截去，再拼接一段新的航线，我们可以有任何细节的嵌套，而且可以充分利用一切可能有用的选项。」「当然，我们现在还不需要这些选择。当不需要这些航线分段和不同的“门航段”时，不使用COMPOSITE模式也能很好地工作。设计模式应该仅仅在需要的时候才使用。」（10260–10262、10263–10264，断行已拼接）；图12-9（行10304–10322，OCR 残缺）：对象图元素（按 OCR 顺序）：complete、Composite Route、deep sea：Composite Route、inbound；Composite Route（OCR『；』应为『：』）、destination、DoorLsg（OCR 应为 Door Leg）、Lcg／ilcg／LLSg／iLeg（OCR 均应为 leg）、Load2;Port Qperation／unload2:Port Qperation（OCR 应为 Load2:Port Operation／unload2:Port Operation）、「…等等」；行10314「12」、行10323「319」为页码噪声；图注：「图12-9 表示了一个完整Route的实例」（10322）。

### 12-10 12.3 为什么没有介绍 FLYWEIGHT｜PDF248｜行10329–10343
- 「由于第5章中提到过FLYWEIGHT模式，因此你可能认为它是一种适用于领域模型的模式。事实上，FLYWEIGHT虽然是设计模式的一个典型的例子，却并不适用于领域模型。」（10332–10333，断行已拼接）
- 「当一个VALUE OBJECT集合（其中的值对象数目有限）被多次使用的时候（例如房屋规划中电源插座的例子），那么把它们实现FLYWEIGHT可能是有意义的。这是一个适用于VALUE OBJECT（但不适用于ENTITY）的实现选择。」（10334–10336，断行已拼接）
- 「COMPOSITE模式与它的不同之处在于，组合模式的概念对象是由其他概念对象组成的。这使得组合模式既适用于模型，也适用于实现，这是领域模式的一个基本特征。」（10336–10338，断行已拼接）
- 「我并不打算把那些可以当作领域模式使用的设计模式完整地列出来。虽然我想不出一个把“解释器”（interpreter）用作领域模式的例子，但我也不能断言解释器不适用于任何一种领域概念。把设计模式用作领域模式的唯一要求是这些模式能够描述关于概念领域的一些事情，而不仅仅是作为解决技术问题的技术解决方案。」（10339–10342，断行已拼接）——行10343「安验」为章末 OCR 噪声。