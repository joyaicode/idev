# HeadFirst《设计模式》精读笔记：第9-10章
（源文件：scripts/docs/notes/HeadFirst设计模式-OCR.txt，本笔记覆盖 L14880-19989；文中行号均指该 OCR 文本行号）

# 第9章 迭代器与组合模式（L14920-L18222）

## 一、问题场景（这个模式解决什么问题，书中原始案例）

对象村餐饮并购案：煎饼屋（PancakeHouseMenu，用 ArrayList 存菜单项）与餐厅（DinerMenu，用定长数组存菜单项）合并，女招待（Waitress）需打印两家全部菜单。因两家内部表示不同，女招待被迫为每家写一个专属循环、直接耦合具体实现；咖啡厅（CafeMenu，用 Hashtable）加入后遍历代码再翻倍；最后 CEO 要求在餐厅菜单内嵌甜点子菜单，"菜单里套菜单"使扁平集合失效，需要树形的"整体/部分"层次。

本章要解决的三层问题：
1. 客户不应知道聚合的内部表示（章末要点 L17973-17975）。
2. 菜单类同时承担"管理菜单项集合"与"提供遍历"两项责任，违反单一责任（L16080-16082）。
3. 部分-整体层次要求客户对个别对象与组合对象一视同仁（L16802-16804）。

## 二、模式解法（结构、参与者、关键机制）

### 迭代器模式（定义 L15875-15877）
提供一种方法顺序访问一个聚合对象中的各个元素，而又不暴露其内部的表示。

参与者：
- Iterator 接口：hasNext()/next()（java.util 版另有 remove()）
- ConcreteIterator：封装对具体聚合结构的遍历（数组版手写步进；ArrayList 版直接复用 java.util）
- Aggregate 接口（Menu）：声明 createIterator()
- ConcreteAggregate（各家菜单）：按自己的内部表示造出合适迭代器

关键机制：把遍历职责从聚合抽出、封装成独立对象（L17976-17977）；女招待只面向 Menu + Iterator 编程；迭代器成为通用接口后，遍历聚合可用多态（L17980-17984）。聚合更换内部表示（数组↔ArrayList↔Hashtable）时客户零改动。

### 组合模式（定义 L16802-16804）
允许你将对象组合成树形结构来表现"整体/部分"的层次结构。组合能让客户以一致的方式处理个别对象和对象组合。

参与者：
- Component（MenuComponent 抽象类）：为叶与组合统一接口；对叶无意义的操作默认抛 UnsupportedOperationException（L17017-17048）
- Leaf（MenuItem）：实现菜单项级操作
- Composite（Menu）：持有子组件集合（含子菜单），操作递归下放

关键机制：Menu.print() 取子组件迭代器递归（L17224-17234）；女招待只持顶层组合，一次 print() 遍历整棵树；外部遍历组合用 CompositeIterator——以 Stack 保存各级迭代器位置（L17506-17563）；叶的 createIterator() 返回 NullIterator 免判空（L17606-17643）。

## 三、关键代码例（要点级转述）

1. Iterator 接口（约 L15450-15490）：
```java
public interface Iterator {
    boolean hasNext();
    Object next();
}
```

2. 聚合各自适配迭代器：
```java
// 餐厅（数组）：手写迭代器
public Iterator createIterator() { return new DinerMenuIterator(items); }
// 煎饼屋（ArrayList）：复用 java.util
public Iterator createIterator() { return menuItems.iterator(); }
// 咖啡厅（Hashtable）：取 values 的迭代器
public Iterator createIterator() { return menuItems.values().iterator(); }
```

3. 女招待统一遍历（一个循环通吃各家菜单）：
```java
void printMenu(Iterator it) {
    while (it.hasNext()) { MenuItem mi = (MenuItem) it.next(); /* ... */ }
}
```

4. MenuComponent 对叶无意义的操作默认抛异常（L17017-17048）：
```java
public void add(MenuComponent c) { throw new UnsupportedOperationException(); }
public void print() { throw new UnsupportedOperationException(); }
```

5. 组合递归打印（Menu.print，L17224-17234）：
```java
public void print() {
    Iterator it = menuComponents.iterator();
    while (it.hasNext())
        ((MenuComponent) it.next()).print();  // 叶打印自己；组合再递归
}
```

6. CompositeIterator 外部遍历（L17506-17563）：next() 取出的若是组合，把它的 createIterator() 压入 java.util.Stack——遍历位置全在迭代器对象内维护，组合层次本身不感知。

7. NullIterator（L17606-17643）：hasNext() 恒返回 false；叶节点返回它而非 null，客户遍历代码零判空分支。

## 四、OO 原则框（本章亮出的原则/要点，注明行号）

- 新亮出：单一责任原则——"一个类应该只有一个引起变化的原因"（L16080-16082）；设计箱收入为"类应该只有一个改变的理由"（L17950）；要点栏强调"我们应该努力让一个类只分配一个责任"（L17985-17986）。
- 既有原则集中兑现：封装变化（菜单内部表示）；针对接口编程（女招待面向 Menu/Iterator）；开放-关闭（三份重复 printMenu 为反例，L16624 附近；方案为菜单收进统一集合一次遍历）；多用组合少用继承（女招待组合迭代器/组合树）。

## 五、章末要点（L17972-17999 原话级概括）

- 迭代器允许访问聚合的元素，而不需要暴露它的内部结构。
- 迭代器将遍历聚合的工作封装进一个对象中。
- 当使用迭代器的时候，我们依赖聚合提供遍历。
- 迭代器提供一个通用接口遍历聚合的项，编码使用聚合的项时可用多态机制。
- 我们应该努力让一个类只分配一个责任。
- 组合模式提供一个结构，可同时包容个别对象和组合对象。
- 组合模式允许客户对个别对象以及组合对象一视同仁。
- 组合结构内的任意对象称为组件；组件可以是组合，也可以是叶节点。
- 实现组合模式有许多设计上的折衷：要按需平衡透明性和安全性。

## 六、判断性论述

1. 客户遍历代码随聚合数据结构分叉（数组/ArrayList/Hashtable 各写一套循环）即违反封装（L17973-17975；习题解答 L18015-18016 明判"女招待需要知道每个菜单如何表达内部的菜单项集合，这违反了封装"）。边界：聚合只有一种且预期不变时无此问题——出现第二种表示或预期会变，就该引入迭代器。
2. 单一责任的可操作判据是数"改变的理由"而非数方法（L16080-16082、L17985-17986）：菜单类因"集合表示要换"与"遍历方式要变"两个理由而改变，即须拆出迭代器对象。
3. "新增一种聚合导致客户加一段循环"是开放-关闭失败的判据（L16624 附近三份重复 printMenu；习题解答 L18017-18020 明言加第三种菜单就要第三个循环）：达标解是把聚合对象收进统一集合、客户一次遍历。
4. 组合模式仅当存在"整体/部分"树形层次时适用（L16802-16804；L17778-17780"当对象彼此间有整体/部分关系、且要用一致方式对待这些对象时才需要组合"）：扁平并列聚合用迭代器即止，无嵌套不造树。
5. 透明性 vs 安全性是有意识的折衷，书中选透明性并自曝代价（L17417-17439、L17972-17999 末条、组合模式访谈 L17766-17868）：统一接口使叶带 add/remove 等无意义方法（默认抛异常，误用只能运行时暴露）；安全版（叶/组合分接口）则要求客户先 instanceof 判型，失去一致处理。书中立场：按应用平衡，无普适答案。
6. try/catch 不应用于表达程序流程（L17749-17750 原话"try/catch 是一种错误处理的方法，而不是程序逻辑的方法"）；本章在 printVegetarianMenu 中仍用它处理"Menu 不支持 isVegetarian"，理由有三（L17751-17762）：instanceof 替代会失去透明性；让 isVegetarian 返回 false 语义不等（"不支持"≠"是 false"）；为后来者实现合理的 Menu.isVegetarian 留扩展空间而不必改此处代码。边界：仅当"不支持该操作"是明确领域语义时，才允许异常驱动控制流。
7. 空对象优于返回 null（L17606-17643）：叶 createIterator() 返回 NullIterator（hasNext 恒 false）而非 null，遍历代码免判空——空对象模式在组合遍历中的落地。

---

# 第10章 状态模式（L18223-L19989）

## 一、问题场景（这个模式解决什么问题，书中原始案例）

万能糖果公司的糖果机（GumballMachine）：四个状态——糖果售罄（SoldOut）/没有25分钱（NoQuarter）/有25分钱（HasQuarter）/售出糖果（Sold）；四个动作——投入25分、退回25分、转动曲柄、发放糖果（dispense 为内部动作，由机器自己调用，L18357-18358）。

第一版实现：整型常量表示状态（final static int SOLD_OUT = 0 等，L18336-18340），每个动作方法内用 if/else if 链对每个状态分支处理（L18365-18394 给出"用实例变量持有状态值 + 方法内条件代码"的通用技巧；L18407-18533 完整实现），功能正确并通过测试（L18558-18663）。

变更请求引爆问题：CEO 要求 10% 概率"赢家"游戏——掉两颗糖果（L18668-18693）。代价：每个方法都要加一个新条件分支处理"赢家"状态，turnCrank 尤其一团乱（L18732-18740）。书中自我诊断（L18742-18751）：未遵守开放-关闭原则；状态转换被埋藏在条件语句中、并不明显；未把会变的部分封装起来；未来加入的代码很可能导致 bug。

## 二、模式解法（结构、参与者、关键机制）

重构路线（L18757-18780）：局部化每个状态的行为（封装变化，L18767）；每个状态的行为放进各自的类，糖果机把动作委托给代表当前状态的对象（多用组合少用继承，L18772）；新状态的加入被局限在小范围（L18777-18779）。三步走（L18791-18796）：①定义 State 接口，每个动作一个方法；②为每个状态实现状态类；③摆脱条件代码，动作全部委托给状态类。

定义（L19261-19262）：状态模式允许对象在内部状态改变时改变它的行为，对象看起来好像修改了它的类。

结构（类图 L19271-19295）：
- Context（GumballMachine）：持有 State 引用与全部状态实例；动作方法一行委托；提供 setState() 与 releaseBall() 辅助方法
- State 接口：insertQuarter()/ejectQuarter()/turnCrank()/dispense()（L18817-18822）
- ConcreteState（NoQuarter/HasQuarter/Sold/SoldOut/Winner）：各自实现本状态下的全部动作

关键机制：
- "看起来修改了类"由组合造成假象：Context 引用不同的状态对象（L19267-19269），客户对状态对象浑然不觉（L19309-19310）。
- 状态类经构造器注入 Context 引用；转换时调 gumballMachine.setState(gumballMachine.getXxxState())（L18935、L19082-19085）——用 getter 而非硬编码具体状态类，把状态类间的依赖降到最小（L19349-19352）。
- Context 不公开 dispense() 动作：turnCrank() 内先委托 state.turnCrank() 再调 state.dispense()（L19034-19041）。
- 全部状态对象在 Context 构造器中一次性创建并持有（L19008-19023），机器的当前状态总是这些实例之一。

## 三、关键代码例（要点级转述）

1. 旧版的条件状态机（L18432-18450）：insertQuarter() 内 if (state == SOLD_OUT) 报错；else if (state == NO_QUARTER) 收钱置 HAS_QUARTER；else if (state == HAS_QUARTER) 重复投币警告；else if (state == SOLD) 已投币警告——每个动作都要穷举全部状态。

2. State 接口（L18817-18822）：四个方法对应四个动作，全部状态类都实现它，不合逻辑的动作也要实现（打印"不该发生"的提示，L18935-18936）。

3. Context 动作变纯委托（L19025-19057）：

```
public void insertQuarter() { state.insertQuarter(); }
public void turnCrank() {
    state.turnCrank();
    state.dispense();   // dispense 不对客户公开
}
public void setState(State s) { state = s; }
public void releaseBall() {
    count--; print("糖果出来啦");
    if (count == 0) state = soldOutState;
}
```

4. 状态类自己发起转换（NoQuarterState，L18922-18955）：insertQuarter() 打印收钱并调 machine.setState(machine.getHasQuarterState())；ejectQuarter()/turnCrank()/dispense() 打印"本状态不该发生"。

5. 随机赢家判定（SoldState.dispense，L19444-19473）：releaseBall 后 `int winner = random.nextInt(10); if (winner == 0 && count > 1) machine.setState(machine.getWinnerState()); else machine.setState(machine.getSoldState());`——一行条件锁定 10% 概率。

6. WinnerState 独立成类（L19392-19435）：dispense() 连续 releaseBall() 两次再转 SoldState；与 SoldState 高度相似但宁可重复也要独立（理由见判断⑤）。

7. refill 补货（L19672-19710/L19979-19984）：SoldOutState 增加 refill()——重新进货并转 NoQuarterState，使糖果机可循环复用而非一次性对象。

## 四、OO 原则框（本章亮出的原则/要点，注明行号）

本章设计箱**无新增 OO 原则**（L19733-19793 明确"这一章我们增加了一个新模式，但在原则方面没有增加任何新的东西"），是既有原则的集中兑现：
- 封装变化（L18767）：把每个状态的行为局部化封装进各自的类
- 多用组合，少用继承（L18772）：糖果机组合一个 State 对象并委托
- 开放-封闭（L18742-18744 诊断旧版违反；L19184-19185）：新状态/新行为只需加一个类，不改既有类
- 委托而非继承（L19923-19959）：习题解答再次确认 Context→State 的委托结构

## 五、章末要点（书中"要点"栏的原话级概括，L19769-19793）

1. 状态模式允许对象基于内部状态而拥有不同的行为。
2. 使用模式利用一个对象（Context）把动作委托给状态对象。
3. Context 拥有状态对象（全部状态实例），动作方法一行转发。
4. 状态转换可以由 State 类或 Context 控制（谁发起转换取决于"对谁修改封闭"）。
5. 状态转换的发起也可以在状态类之间进行（状态类经 getter 相互引用）。
6. 状态模式会使类数目大量增加——这是为弹性付出的明码标价。
7. 状态类可以被多个 Context 实例共享（前提：不持有自己的内部状态）。
8. 状态模式与策略模式类图相同、意图不同：策略配置 Context 一次性行为（继承的弹性替代），状态让状态对象游走、Context 随状态改变行为（条件判断的弹性替代）。
9. dispense() 这类内部动作不进 State 公开接口语义，由 Context 在动作序列中自行调用。
10. 测试驱动验证：新架构下"赢家"只是新增一个状态类 + SoldState 内一处判定（L19489-19555）。

## 六、判断性论述

1. **状态转换埋藏在条件语句中 = 重构信号**（L18748-18749、L19362-19367）：书中明确"状态转换埋藏在条件语句中，并不明显"是旧版的罪状之一，状态模式正是"把条件判断弹性化"的替代（L19321-19323）。边界：状态数稳定（2-3 个）且永不扩展时，条件写法不构成违例；一旦新增状态需要改动多个方法的 if/else 链（如"赢家"变更，L18732-18740），即触发重构。

2. **状态 vs 策略看意图不看结构**（L19304-19323、L19603-19667）：两者类图一模一样，差别只在意图——策略是客户配置 Context、通常只配一次；状态是 Context 随事件把行为切来切去、客户浑然不觉。同一个结构，因使用意图不同而是两个模式。这排除了"按类图选模式"的做法。

3. **状态转换的归属有明确规则**（L19339-19355）：转换固定不变时放 Context（状态类不互相依赖）；转换动态、依赖运行时条件时放状态类。判据是"想让谁对修改封闭"。

4. **类数膨胀是明码标价，不构成拒绝理由**（L19356-19361）：书中直言状态模式"会造成类数目的增加"，但"绝对值得"，弹性是其回报；真正的标尺是暴露给客户的类数（客户只面对 Context，状态类是内部细节，L19369-19375）。

5. **一个状态一个类，清晰优先于消重复**（L19556-19564）：WinnerState 与 SoldState 代码高度相似，书中仍选择独立成类——"一个类、一个责任"，把行为放进一个类带来的清晰，胜过容忍代码重复。边界：仅当两个状态行为真的相同到可合并时才合并，"相似"不是合并理由。

6. **客户不得直接与状态对象交互**（L19369-19375）：状态对象是 Context 的内部细节，Context 是客户唯一对话对象；状态类不向客户暴露。

7. **状态实例共享的前提是它不持有内部状态**（L19378-19390）：无实例变量的状态类可提为静态实例被多个 Context 共享，需要 Context 数据时把 context 作参数传入方法——这是享元思路在状态上的应用，有内部状态的状态类禁用此优化。