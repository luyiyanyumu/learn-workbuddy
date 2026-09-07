#!/usr/bin/env python3
# [原第 1 行] 这是 shebang（解释器提示行）。在支持它的 Unix 类系统里，直接执行脚本时，会通过 /usr/bin/env 在 PATH 中寻找 python3。它对 Python 本身是注释；Windows 中通常用 python 文件名.py 来启动。
# [原第 2 行] 从 __future__ 导入 annotations，启用推迟处理类型注解的行为，避免定义函数时立即求出注解中的类型。这让后面的 -> AgentTurn 能引用当时尚未定义完成的类；它不会自动检查实际参数类型。 常规理解是“先记下类型说明，稍后需要时再处理”；这里不意味着导入整个 annotations 模块供你调用。
from __future__ import annotations
"""
s01_agent_loop.py - The Agent Loop

The entire secret of a desktop AI assistant in one pattern:

    while the turn contains tool calls:
        response = LLM(messages, tools)
        execute tools
        append results

    +----------+      +-------+      +---------+
    |   User   | ---> |  LLM  | ---> |  Tool   |
    |  prompt  |      |       |      | execute |
    +----------+      +---+---+      +----+----+
                          ^               |
                          |   tool_result |
                          +---------------+
                          (loop continues)

This is the core loop: feed tool results back to the model until the model
returns a turn without tool calls. WorkBuddy's production-style agent bridge
starts with this loop, then adds the surrounding harness mechanisms taught in
later chapters.

Usage:
    pip install anthropic python-dotenv
    ANTHROPIC_API_KEY=... MODEL_ID=... python s01_agent_loop/code.py
"""

# [原第 32 行] import os 导入标准库 os。后面通过 os.getcwd() 获取工作目录，通过 os.getenv()/os.environ 读取或修改环境变量。
import os
# [原第 33 行] 导入标准库 subprocess，用来启动外部命令、等待结束并读取输出。真正执行工具的功能来自它。
import subprocess
# [原第 34 行] 从 dataclasses 模块只导入 dataclass。from 模块 import 名字 可以直接使用这个名字，后面用它给类自动生成初始化等方法。
from dataclasses import dataclass
# [原第 35 行] 从 enum 模块导入 Enum（枚举类），用来列出固定的停止原因，减少四处手写字符串造成的拼写错误。
from enum import Enum
# [原第 36 行] 从 typing 模块导入 Any，表示该类型注解允许任意类型。Any 是给阅读者和类型检查工具看的，不会把数据转换成某种类型。
from typing import Any


# [原第 39 行] 普通注释：接下来的内容是机器可读取的课程进度元数据。# 到行尾是注释，不作为 Python 语句运行。
# Machine-readable learning path metadata. Tests enforce that every
# [原第 40 行] 接上一行：注释声称项目测试会检查每章继承和新增了什么。此文件只声明数据，没有提供这些测试。
# chapter declares what it inherits and what it adds.
# [原第 41 行] 创建字典并赋给 PROGRESSION。字典用 { } 包围，每个条目是 键: 值；变量名全大写表示按约定当作常量，Python 不会强制禁止修改。
PROGRESSION = {
    # [原第 42 行] 字典条目：键 chapter 对应字符串 s01_agent_loop，标明当前章节。结尾逗号用来分隔条目。
    "chapter": "s01_agent_loop",
    # [原第 43 行] 键 builds_on 对应空列表 []，表示元数据中没有列出前置章节。列表可以按顺序存放多个元素。
    "builds_on": [],
    # [原第 44 行] 键 adds 对应一个列表；本行的 [ 开始列出本章新增的能力，后续几行属于这个列表。
    "adds": [
        # [原第 45 行] adds 列表的第一个字符串元素：最小智能体循环。字符串必须用引号包围。
        "minimal agent loop",
        # [原第 46 行] 第二个字符串元素：一个名为 bash 的工具。这是能力描述，不会在此处执行命令。
        "single bash tool",
        # [原第 47 行] 第三个字符串元素：通过 tool_use（调用请求）和 tool_result（执行结果）形成反馈。
        "tool_use/tool_result feedback",
        # [原第 48 行] 第四个字符串元素：明确约定循环因为什么停止。contract 在这里是接口行为约定，不是 Python 特殊语法。
        "explicit loop stop contract",
    # [原第 49 行] 用 ] 结束 adds 列表，随后的逗号表示字典中还有下一项。括号没有闭合时，Python 允许自然换行。
    ],
    # [原第 50 行] 键 preserves 对应包含一个字符串的列表，表示保留交互式 CLI（命令行界面）能力。
    "preserves": ["interactive CLI"],
# [原第 51 行] 用 } 结束 PROGRESSION 字典。大括号负责字典结构，后面的函数和控制流程则依靠缩进组织。
}

# [原第 53 行] 注释说明辅助入口的设计意图：--demo 做离线演示，--provider deepseek 准备真实服务的环境配置。参数解析代码在外部模块中，这里看不到其具体实现。
# Shared learning entrypoints: --demo is offline; --provider deepseek configures real API env.
# [原第 54 行] 导入 sys 并用 as 起别名 _wb_sys。sys.path 保存 Python 搜索模块的目录；开头下划线表示内部使用的命名约定，不是访问权限限制。
import sys as _wb_sys
# [原第 55 行] 从 pathlib 导入 Path 并起别名 _wb_Path。Path 把路径变成可操作的对象，比反复拼接路径字符串方便。
from pathlib import Path as _wb_Path

# [原第 57 行] __file__ 是当前文件路径；Path(...) 包装路径，resolve() 得到解析后的绝对路径，parents[1] 取祖父目录。索引从 0 开始：parents[0] 是父目录。代码假设脚本位于 项目根/s01_agent_loop/code.py 这样的层级。
_WB_ROOT = _wb_Path(__file__).resolve().parents[1]
# [原第 58 行] str(_WB_ROOT) 将路径对象转成字符串；not in 判断它是否不在模块搜索目录列表中；if 条件后的冒号开启一个缩进代码块。
if str(_WB_ROOT) not in _wb_sys.path:
    # [原第 59 行] 若根目录不在 sys.path 中，insert(0, ...) 把它插到第 0 个位置，即列表最前面，提高搜索优先级。只改当前 Python 进程的搜索路径，不是修改操作系统的 PATH。
    _wb_sys.path.insert(0, str(_WB_ROOT))
# [原第 60 行] 从项目自己的 mini_workbuddy.chapter_demo 模块导入函数并起别名。它不是 Python 标准库；单独复制此文件并不包含这个模块。
from mini_workbuddy.chapter_demo import maybe_run_chapter_demo as _wb_maybe_run_chapter_demo

# [原第 62 行] 调用辅助函数，传入当前文件路径和章节字典。是否因 --demo 执行演示并退出，要看外部实现；仅凭这一行不能断言它必定退出。
_wb_maybe_run_chapter_demo(__file__, PROGRESSION)
# [原第 63 行] 继续从同一个项目模块导入服务配置准备函数，并起别名 _wb_prepare_chapter_provider。
from mini_workbuddy.chapter_demo import prepare_chapter_provider as _wb_prepare_chapter_provider

# [原第 65 行] 用空括号调用函数，不显式传参数；它可能读取命令行参数或环境，但具体修改了什么必须查看函数源码。本行位于顶层，导入模块时也会运行。
_wb_prepare_chapter_provider()

# [原第 67 行] try: 开始尝试执行一段可能抛出异常的代码。若出现匹配的异常，会跳到后面的 except，而不是直接继续剩余的 try 代码。
try:
    # [原第 68 行] 尝试导入 readline，为交互式输入提供行编辑等能力。有些环境没有这个模块，此处用异常处理兼容。
    import readline

    # [原第 70 行] 调用 readline.parse_and_bind() 传入配置文本。该项关闭 Readline 根据终端驱动特殊字符自动重设对应键绑定的行为；不是禁用所有快捷键。
    readline.parse_and_bind("set bind-tty-special-chars off")
    # [原第 71 行] input-meta on 允许输入保留第 8 位，不把输入强行限制成 7 位字符。
    readline.parse_and_bind("set input-meta on")
    # [原第 72 行] output-meta on 让高位字符直接输出，而不是显示成转义形式。这些设置与终端字符处理有关。
    readline.parse_and_bind("set output-meta on")
    # [原第 73 行] convert-meta off 禁止把高位输入字节转换成 ESC 前缀序列。这几项有助于多字节字符输入，但并不单独保证中文编码正确。
    readline.parse_and_bind("set convert-meta off")
# [原第 74 行] except ImportError: 只处理 try 中发生的导入错误。并非捕获所有错误；其他异常仍可能向外抛出。
except ImportError:
    # [原第 75 行] pass 是空操作，表示这里有意不做任何处理。发生上述导入错误后，程序继续执行后面的代码。
    pass

# [原第 77 行] 从第三方 anthropic 包导入 Anthropic 客户端类，后面用它创建 API 客户端。import 不等于已经请求模型。
from anthropic import Anthropic
# [原第 78 行] 从第三方 dotenv 包导入 load_dotenv，用于读取 .env 配置文件。安装包叫 python-dotenv，导入模块叫 dotenv。
from dotenv import load_dotenv

# [原第 80 行] 调用 load_dotenv() 把找到的 .env 配置加载到进程环境中；override=True 表示文件中存在的同名配置可以覆盖已有环境变量。具体查找位置与调用环境有关，不能一概说只读当前目录。
load_dotenv(override=True)

# [原第 82 行] os.getenv() 读取 ANTHROPIC_BASE_URL；未设置时返回 None。if 检查其真假：缺失或空字符串时不进入下面分支。
if os.getenv("ANTHROPIC_BASE_URL"):
    # [原第 83 行] 从当前进程的环境变量映射中删除 ANTHROPIC_AUTH_TOKEN。pop(键, None) 在键不存在时返回 None 而不报 KeyError。可理解为自定义服务地址时清掉另一种认证配置，但作者确切动机未在此解释；不会永久删除系统设置。
    os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)

# [原第 85 行] 创建 Anthropic 客户端对象并保存为 client；base_url= 是按参数名传值。服务地址来自环境变量；未显式传 api_key 时，SDK 默认可读取 ANTHROPIC_API_KEY。创建客户端不等于这里已生成模型回答。
client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))
# [原第 86 行] 读取 MODEL_ID 并保存到 MODEL。os.environ.get() 类似字典 get()：键缺失时返回 None，不像 os.environ[键] 那样抛 KeyError。
MODEL = os.environ.get("MODEL_ID")
# [原第 87 行] not MODEL 在 MODEL 是 None 或空字符串时成立。它没有检查该字符串是否为真实可用的模型名，也没有剔除纯空格。
if not MODEL:
    # [原第 88 行] raise 主动抛出 SystemExit 异常，请求结束程序，并携带后面的说明文字。顶层未捕获它时程序退出。
    raise SystemExit(
        # [原第 89 行] 错误信息的前半段，要求配置 MODEL_ID，并把 .env.example 复制为 .env 后填写参数。这只是错误提示，没有实际执行文件复制。
        "MODEL_ID is not set. Copy .env.example to .env and fill in "
        # [原第 90 行] 错误信息的后半段。Python 会把括号内相邻的字符串字面量自动拼接，不需要写 +；前一行末尾的空格用于衔接文字。
        "ANTHROPIC_API_KEY and MODEL_ID (see README quick start)."
    # [原第 91 行] 关闭 SystemExit(...) 的调用括号。整段第 88—91 行合起来是一条 raise 语句。
    )

# [原第 93 行] 创建系统提示词 SYSTEM。f 前缀表示格式化字符串，{os.getcwd()} 会被当前工作目录替换。内容要求该脚本里的模型通过工具行动；它只是这个程序要发送的数据，不是当前代码讲解的指令。
SYSTEM = f"You are a coding agent at {os.getcwd()}. Use bash to solve tasks. Act, don't explain."
# [原第 94 行] 给默认最大模型调用轮数赋值 8。它限制单次 agent_loop 中的外层模型请求次数，不限制整个聊天只能输入 8 次，也不限制工具总数为 8。
MAX_TURNS = 8

# [原第 96 行] 注释标明下面定义唯一的工具。工具说明和真正执行工具的函数是两部分。
# -- Tool definition: just bash --
# [原第 97 行] 开始创建工具列表 TOOLS。API 使用列表形式，方便描述多个工具；这里实际只放了一个。
TOOLS = [
    # [原第 98 行] 列表中的第一个元素是字典，本行 { 开始这个工具的说明。
    {
        # [原第 99 行] 工具名设置为 bash，模型生成调用请求时用这个名称标识工具。名称本身不会安装 Bash，也不会自动绑定到 run_bash 函数。
        "name": "bash",
        # [原第 100 行] description 是给模型看的自然语言说明：“运行一条 shell 命令”。它帮助模型了解工具用途。
        "description": "Run a shell command.",
        # [原第 101 行] input_schema 开始描述工具参数的 JSON Schema。这里的内容在 Python 中写成嵌套字典，随后由 SDK 序列化。
        "input_schema": {
            # [原第 102 行] 参数整体要求为 object，对应本例中的 Python 字典，例如 {'command': 'echo hello'}。
            "type": "object",
            # [原第 103 行] properties 声明 command 这个字段，其类型要求为 string（字符串）。这里的两个冒号都在表达字典键值关系。
            "properties": {"command": {"type": "string"}},
            # [原第 104 行] required 列表列出必填字段 command。必填并不表示非空，空字符串还要由第 205 行检查。
            "required": ["command"],
        # [原第 105 行] 关闭 input_schema 的字典。末尾逗号允许保留，叫作尾随逗号。
        },
    # [原第 106 行] 关闭这一项工具说明字典。
    }
# [原第 107 行] 关闭整个 TOOLS 列表。到此只是公布工具接口，尚未执行任何系统命令。
]


# [原第 110 行] 注释：接下来用类表达每轮响应和循环停止的约定，让不同部分用统一结构交流。
# -- Explicit turn and stop contracts --
# [原第 111 行] class 定义 LoopStopReason 类，括号表示继承 str 和 Enum。它是带字符串值的枚举，合法原因集中写在类中；冒号后是类体。
class LoopStopReason(str, Enum):
    # [原第 112 行] 这是类体第一条语句，所以该三引号字符串是类的文档字符串，可通过 __doc__ 获取。harness 指管理模型调用、工具执行和停止条件的运行代码。
    """Why the harness stopped asking the model for another turn."""

    # [原第 114 行] 枚举成员 FINAL_ANSWER 的值为字符串 final_answer，表示本程序把这次停止归类为最终回答。成员是枚举对象，取原始字符串用 .value。
    FINAL_ANSWER = "final_answer"
    # [原第 115 行] 枚举成员 MAX_TOKENS 表示模型这轮触及生成 token 上限的停止分类。
    MAX_TOKENS = "max_tokens"
    # [原第 116 行] 枚举成员 MAX_TURNS 表示本地循环到达轮数上限。它和文件级变量 MAX_TURNS 名字相同但作用域不同：一个是枚举成员，一个是数字 8。
    MAX_TURNS = "max_turns"


# [原第 119 行] @ 开头的是装饰器；dataclass 为下方类生成 __init__、__repr__ 等方法。frozen=True 阻止普通的字段重新赋值，但字段指向的字典或列表仍能在内部被修改，并非深度冻结。
@dataclass(frozen=True)
# [原第 120 行] 定义 ToolInvocation 数据类，表示一次工具调用请求。可把它当成填写“编号、工具名、参数”的表格模板。
class ToolInvocation:
    # [原第 121 行] 类文档字符串：仅保存本章需要的工具调用信息，尽量减少后续代码对服务商对象格式的依赖。
    """The small provider-neutral slice of a tool_use block needed by s01."""

    # [原第 123 行] 声明 tool_use_id 字段，类型注解为 str，用于关联调用请求和返回结果。这里是“变量名: 类型”，不是字典条目；dataclass 会把它纳入构造函数参数。
    tool_use_id: str
    # [原第 124 行] 声明 name 字段，记录工具名称，类型注解是字符串。在后续执行函数里实际没有验证它是否等于 bash。
    name: str
    # [原第 125 行] 声明 arguments 字段为字典；dict[str, Any] 表示键是字符串，值可以是任意类型，例如 {'command': 'echo hello'}。注解不会在运行时自动验证字段内容。
    arguments: dict[str, Any]


# [原第 128 行] 同样给 AgentTurn 应用冻结数据类装饰器，自动生成常用方法，并限制对字段本身重新赋值。
@dataclass(frozen=True)
# [原第 129 行] 定义 AgentTurn，表示整理过的一次模型响应，不是整场对话。
class AgentTurn:
    # [原第 130 行] 类文档字符串：先把模型响应统一格式化，再由外面的循环决定继续还是停止。
    """One normalized model turn, before the harness decides what to do next."""

    # [原第 132 行] content 字段保存完整响应内容块列表，list[Any] 表示列表元素类型不作限制。这有助于回传完整消息，而不只保存提取出的文字。
    content: list[Any]
    # [原第 133 行] provider_stop_reason 保存服务端的停止原因；str | None 是联合类型注解，表示字符串或 None（没有提供该信息）。| 在这里不是 shell 管道。
    provider_stop_reason: str | None
    # [原第 134 行] tool_calls 是由零个或多个 ToolInvocation 组成的元组。tuple[T, ...] 中的 ... 表示可以有任意数量的 T 元素；元组本身不能增删元素。
    tool_calls: tuple[ToolInvocation, ...]
    # [原第 135 行] text 字段保存从这一轮响应中汇总出的文字，类型为 str。
    text: str

    # [原第 137 行] @classmethod 把下面的函数变成类方法。调用 AgentTurn.from_response(...) 时，Python 自动把类 AgentTurn 作为第一个参数 cls 传入，不必先创建实例。
    @classmethod
    # [原第 138 行] def 定义类方法，cls 指调用它的类；response: Any 是参数注解；-> AgentTurn 是返回值注解；冒号开启方法体。它的职责是把 SDK 响应转换成自己的数据类。
    def from_response(cls, response: Any) -> AgentTurn:
        # [原第 139 行] 方法文档字符串：文字和工具调用只提取一次，避免不同位置重复解析导致判断不一致。
        """Read text and tool calls once so loop decisions use one source of truth."""

        # [原第 141 行] 从内到外读：getattr(response, 'content', []) 读取对象的 content 属性，属性缺失时用 []；or [] 又把 None 等假值替换为空列表；list(...) 转为新列表。这是浅复制，而且不保证能兼容任意错误类型。
        content = list(getattr(response, "content", []) or [])
        # [原第 142 行] 创建空列表 text_parts，用来临时收集文字片段；list[str] 表示元素预期是字符串。冒号部分是注解，= [] 才是实际赋值。
        text_parts: list[str] = []
        # [原第 143 行] 创建空列表 tool_calls，临时收集解析出的 ToolInvocation 对象。此处先用方便 append 的列表，最后再转成元组。
        tool_calls: list[ToolInvocation] = []

        # [原第 145 行] for ... in ... 依次遍历 content 中的内容块，每次把一个元素放入 block，再执行下面缩进的代码。
        for block in content:
            # [原第 146 行] 读取当前块的 type 属性，缺失时返回 None。getattr 访问的是对象属性，不等同于从普通字典中用 get('type') 取键。
            block_type = getattr(block, "type", None)
            # [原第 147 行] == 比较 block_type 是否等于字符串 text。如果相等，说明这是文字块；不要把 ==（比较）与 =（赋值）混淆。
            if block_type == "text":
                # [原第 148 行] 取文字块的 text 属性，缺失时用空字符串；str(...) 转成字符串；append(...) 把它追加到片段列表。若属性存在但为 None，str(None) 会产生文字 'None'，不是空串。
                text_parts.append(str(getattr(block, "text", "")))
            # [原第 149 行] elif 表示“否则再判断”。仅当上一个 if 不成立时，才检查此块是否为 tool_use（工具调用请求）。
            elif block_type == "tool_use":
                # [原第 150 行] 读取工具块的 input 属性作为原始参数，属性缺失时先给空字典 {}。
                raw_arguments = getattr(block, "input", {})
                # [原第 151 行] 条件表达式 A if 条件 else B：若 raw_arguments 是 dict，就用 dict(...) 做一层浅复制，否则使用空字典。它只检查外层类型，不验证 command 等具体字段。 如果 input 是装着 JSON 文本的字符串，此处也不会自动解析 JSON。
                arguments = dict(raw_arguments) if isinstance(raw_arguments, dict) else {}
                # [原第 152 行] 准备把一项工具调用追加到 tool_calls 列表，括号内的参数在后续几行构建。
                tool_calls.append(
                    # [原第 153 行] 调用 ToolInvocation(...) 构造数据类实例，下一步为三个字段传入值。构造方法由 dataclass 自动生成。
                    ToolInvocation(
                        # [原第 154 行] 从块中读取 id，转换为字符串，作为 tool_use_id；属性缺失则用空字符串。这是关联编号的提取，不是创建或校验唯一编号。
                        tool_use_id=str(getattr(block, "id", "")),
                        # [原第 155 行] 读取并转换工具名，存入 name；属性缺失时用空字符串。
                        name=str(getattr(block, "name", "")),
                        # [原第 156 行] 把前面整理好的 arguments 字典传给同名字段。左边 arguments 是参数名，右边 arguments 是当前方法里的变量。
                        arguments=arguments,
                    # [原第 157 行] 关闭 ToolInvocation(...) 调用括号，完成一次工具调用对象的构造。
                    )
                # [原第 158 行] 关闭 tool_calls.append(...)，把上面构造的对象放进列表。这两层括号分别属于不同的函数调用。
                )

        # [原第 160 行] return 返回 cls(...) 创建的新对象并结束方法。因为 cls 通常是 AgentTurn，这相当于创建 AgentTurn(...)；类方法写 cls 也便于子类复用。
        return cls(
            # [原第 161 行] 把原始完整内容列表赋给新对象的 content 字段。
            content=content,
            # [原第 162 行] 从 SDK response 读取 stop_reason，作为 provider_stop_reason；属性缺失时记录 None，保留服务端原始停止信息。
            provider_stop_reason=getattr(response, "stop_reason", None),
            # [原第 163 行] tuple(tool_calls) 把临时列表转换成元组，赋给对象字段。这不是执行工具，只是整理请求信息。
            tool_calls=tuple(tool_calls),
            # [原第 164 行] 用空字符串作为连接符，把 text_parts 拼接为一段文字，例如 ['你', '好'] 变成 '你好'。不会自动添加空格或换行，原有片段内的换行会保留。
            text="".join(text_parts),
        # [原第 165 行] 关闭 cls(...) 构造调用。本方法返回一份含完整内容、原始停止原因、工具请求和文字的 AgentTurn。 对其他类型的块，本方法仍保留其原始 content，只是不把它们加入文字或工具请求列表。
        )


# [原第 168 行] 为最后的结果类应用 dataclass(frozen=True)，用同一种方式生成字段构造方法并限制重新赋值。
@dataclass(frozen=True)
# [原第 169 行] 定义 AgentLoopResult，表示一次 agent_loop 完成后返回给调用方的结果记录。
class AgentLoopResult:
    # [原第 170 行] 类文档字符串：命令行界面、测试或后续运行框架可以读取这个结果，了解此次循环发生了什么。
    """Observable outcome returned to the CLI, tests, or a later harness layer."""

    # [原第 172 行] stop_reason 字段使用 LoopStopReason 枚举，记录本地程序归纳的停止原因，区别于服务端原始字符串。
    stop_reason: LoopStopReason
    # [原第 173 行] turns 字段是整数，记录这次 agent_loop 已完成的模型响应轮数，正常返回时用实际轮次或上限。
    turns: int
    # [原第 174 行] tool_calls 在这个类中是整数，记录已返回结果的工具调用次数；在 AgentTurn 中同名字段却是元组，读代码时要看所属对象。
    tool_calls: int
    # [原第 175 行] final_text 字段保存返回给界面的文字。达到轮数上限时它可能只是最后一轮的文字片段，名字并不保证任务已经完成。
    final_text: str
    # [原第 176 行] provider_stop_reason 保留最后一轮服务端停止原因，可能为字符串，也可能为 None。
    provider_stop_reason: str | None


# [原第 179 行] 注释：下面开始实现工具执行逻辑。上面的 TOOLS 只负责描述接口，这里才负责实际工作。
# -- Tool execution --
# [原第 180 行] def 定义 run_bash 函数；command: str 表示参数预期是命令字符串；-> str 表示返回命令输出或错误说明。执行到 def 时只是定义函数，调用 run_bash(...) 时才运行函数体。
def run_bash(command: str) -> str:
    # [原第 181 行] 创建名为 dangerous 的字符串列表，作为简单拦截规则。这只是硬编码的子串黑名单，不能识别所有危险行为，也可能误拦含有这些文字的普通命令。
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    # [原第 182 行] item in command 检查子串是否出现；for item in dangerous 形成生成器表达式；any(...) 只要遇到一个真值就返回 True 并停止检查。整行表示“命中任意一项就拦截”。
    if any(item in command for item in dangerous):
        # [原第 183 行] 返回错误字符串并立即结束 run_bash，因此不会进入后面的 subprocess.run。返回字符串不等于抛异常，上层仍会把它作为工具结果处理。
        return "Error: Dangerous command blocked"
    # [原第 184 行] 开始 try 块，尝试真正执行命令并处理输出，后面的 except 处理指定异常。
    try:
        # [原第 185 行] 调用 subprocess.run(...) 启动子进程，等待其结束，再把 CompletedProcess 结果对象赋给 completed。它不是在后台发出后就立即返回。
        completed = subprocess.run(
            # [原第 186 行] 把 command 作为第一个位置参数传入，告诉 subprocess 要运行什么命令。
            command,
            # [原第 187 行] shell=True 表示交给系统 shell 解释字符串，因此可以使用管道等 shell 语法。它并未指定 Bash：POSIX 通常是 /bin/sh，Windows 通常由 COMSPEC 指向 cmd.exe。
            shell=True,
            # [原第 188 行] cwd= 指定子进程的工作目录，这里使用 Python 当前工作目录。它不一定等于脚本目录，也不限制命令访问该目录以外的位置。
            cwd=os.getcwd(),
            # [原第 189 行] capture_output=True 捕获标准输出 stdout 和标准错误 stderr，随后可以从 completed 读取；执行时不会把这两路输出直接实时显示给用户。
            capture_output=True,
            # [原第 190 行] text=True 让捕获结果按文本处理，得到字符串而不是 bytes 字节串。代码未指定 encoding，实际解码使用默认设置，不能把它直接理解为强制 UTF-8。
            text=True,
            # [原第 191 行] timeout=120 设置等待命令完成的超时秒数；超时按 subprocess 的机制处理并抛出 TimeoutExpired。它限制此处子进程等待，不是模型 API 请求的超时设置。
            timeout=120,
        # [原第 192 行] 结束 subprocess.run(...) 的参数列表和调用。没有传 check=True，因此非零退出码本身不会自动触发 CalledProcessError。
        )
        # [原第 193 行] 用 + 把 stdout 和 stderr 两个字符串拼接，再用 strip() 去掉两端空白。这种“标准输出在前、标准错误在后”的拼接不保留两路输出原本交错的时间顺序。
        output = (completed.stdout + completed.stderr).strip()
        # [原第 194 行] 如果 output 非空，就返回切片 output[:50000]，即索引 0 到 49999 的最多 50000 个字符串元素；否则返回 '(no output)'。这里按字符切片，不能等同于 50000 tokens；完整输出已先被捕获，并非只捕获这么多。
        return output[:50000] if output else "(no output)"
    # [原第 195 行] 捕获 subprocess.TimeoutExpired，表示上面的命令等待超时。
    except subprocess.TimeoutExpired:
        # [原第 196 行] 超时后返回提示文字 'Error: Timeout (120s)'。上层收到这个普通字符串后仍可把它反馈给模型。
        return "Error: Timeout (120s)"
    # [原第 197 行] 捕获括号中任一种异常，并用 as exc 给异常对象起名。FileNotFoundError 是 OSError 的子类，单独列出它比较直观，但从覆盖范围看有重复。
    except (FileNotFoundError, OSError) as exc:
        # [原第 198 行] 把异常对象格式化到字符串中并返回，例如 Error: 后面接具体系统错误。它没有继续 raise，因此这些被捕获的异常不会直接终止本次循环。
        return f"Error: {exc}"


# [原第 201 行] 定义 execute_bash_call：接收一份 ToolInvocation 请求，返回字符串键、任意值的字典。它负责参数检查、执行、显示和打包结果。
def execute_bash_call(call: ToolInvocation) -> dict[str, Any]:
    # [原第 202 行] 函数文档字符串：执行本章公布的唯一工具，并把结果编码成协议需要的形状。
    """Execute the only tool advertised by s01 and encode its result."""

    # [原第 204 行] 从 call 的 arguments 字典读取 command，键不存在时返回 None。call.arguments 用点访问对象字段，.get('command') 再读取字典键。
    command = call.arguments.get("command")
    # [原第 205 行] 先检查 command 是否不是字符串，或去掉空白后是否为空。or 有短路行为：第一项已为 True 时，不会调用第二项的 strip()，避免对 None 等对象调用字符串方法。
    if not isinstance(command, str) or not command.strip():
        # [原第 206 行] 参数不合格时设置错误输出，不会执行 shell。这里仍会走到第 212 行，把错误包装为工具结果。
        output = "Error: bash requires a non-empty command"
    # [原第 207 行] else: 在上一条 if 条件不成立时执行，也就是 command 确实是非空白字符串时。
    else:
        # [原第 208 行] 打印即将执行的命令。f-string 把 {command} 替换为命令；\033 是 ESC 的八进制转义，后面的 [33m 设置黄色，[0m 恢复颜色。$ 只是展示用的提示符，不是额外执行的命令。
        print(f"\033[33m$ {command}\033[0m")
        # [原第 209 行] 调用 run_bash(command) 真正执行命令，将返回的输出或错误字符串赋给 output。这里没有先检查 call.name 是否为 bash。
        output = run_bash(command)
        # [原第 210 行] 只打印 output 的前 200 个字符，控制终端显示长度；提交给模型的 content 仍使用完整的 output（正常命令输出已在前面最多截到 50000 字符）。
        print(output[:200])

    # [原第 212 行] return { 开始创建并返回结果字典，不是定义新的函数或代码块。
    return {
        # [原第 213 行] 设置结果块的 type 为 tool_result，告诉模型接口这是一项工具执行结果。
        "type": "tool_result",
        # [原第 214 行] 把原请求的 tool_use_id 放回结果，让 API 和模型可以知道这份结果对应哪次工具请求。
        "tool_use_id": call.tool_use_id,
        # [原第 215 行] 把 output 放入 content，既可能是命令输出，也可能是上述 Error: 文本。代码没有另设 is_error 标志。
        "content": output,
    # [原第 216 行] 结束结果字典并返回。execute_bash_call 的返回值不是 AgentLoopResult，而是要加入消息历史的单个工具结果块。
    }


# [原第 219 行] 定义停止判断函数。参数 turn 是整理好的模型轮次；返回值可能是 LoopStopReason 枚举，也可能是 None。
def stop_reason_for(turn: AgentTurn) -> LoopStopReason | None:
    # [原第 220 行] 函数文档字符串：返回 None 表示继续；返回某种停止原因表示结束。None 在这里是特意设计的控制信号，并非错误。
    """Return None to continue, otherwise the explicit harness stop reason."""

    # [原第 222 行] 注释解释设计意图：优先检查实际内容，不单纯信任服务端 stop_reason。注释不会改变代码行为。
    # Inspect content instead of trusting stop_reason alone. This also works
    # [原第 223 行] 接上一行：作者希望兼容内容和停止元信息不同步的服务。此文件实际没有实现流式接收，它只是读取已取得的 response。
    # when a provider reports its stop metadata later than its content blocks.
    # [原第 224 行] 非空工具调用元组在 if 中为真，空元组为假。因此只要包含至少一次工具调用，就走下一行。
    if turn.tool_calls:
        # [原第 225 行] 返回 None，要求继续处理工具。这个分支优先于后面的 max_tokens 检查，即便服务端同时报 max_tokens，也会先按工具分支处理。
        return None
    # [原第 226 行] 只有没有工具调用时，才检查服务端停止原因是否恰好为字符串 max_tokens。
    if turn.provider_stop_reason == "max_tokens":
        # [原第 227 行] 返回本地枚举 MAX_TOKENS，让调用方知道回答可能因生成上限而不完整。
        return LoopStopReason.MAX_TOKENS
    # [原第 228 行] 其余所有没有工具调用的响应都归为 FINAL_ANSWER。这是本代码的默认分类，不是对回答正确性、非空性或任务完成情况的验证。
    return LoopStopReason.FINAL_ANSWER


# [原第 231 行] 注释概括核心模式：调用模型，执行工具块，并按照明确规则停止。
# -- The core pattern: call the model, execute tool blocks, and stop explicitly --
# [原第 232 行] 定义 agent_loop。messages 是由字典组成的列表；max_turns 默认取定义函数时 MAX_TURNS 的值（此处 8）；返回 AgentLoopResult。传入的列表会被原地追加，函数没有先复制它。
def agent_loop(messages: list[dict[str, Any]], max_turns: int = MAX_TURNS) -> AgentLoopResult:
    # [原第 233 行] 检查最大轮数是否小于 1。只做数值比较，没有全面检查参数类型；类型注解不会自动阻止调用者传错类型。
    if max_turns < 1:
        # [原第 234 行] 参数小于 1 时抛出 ValueError，要求调用者纠正。和 run_bash 返回 Error: 字符串不同，这是真正的异常。
        raise ValueError("max_turns must be at least 1")

    # [原第 236 行] 工具调用计数从 0 开始，每调用一次 agent_loop 都重新计数。
    tool_call_count = 0
    # [原第 237 行] last_turn 初始为 None，表示还没有模型响应；注解允许之后把它改成 AgentTurn 对象。
    last_turn: AgentTurn | None = None

    # [原第 239 行] range(1, max_turns + 1) 生成从 1 到 max_turns 的整数，不包含右端点。默认即 1、2、…、8；每次循环尝试取得一份模型响应。
    for turn_number in range(1, max_turns + 1):
        # [原第 240 行] 通过客户端 messages 接口调用 create()，向配置的服务请求下一轮模型响应。这个调用返回后，response 才能用于后面的解析；代码没有使用流式接口。
        response = client.messages.create(
            # [原第 241 行] model=MODEL 指定环境配置中的模型标识。左边 model 是 SDK 参数名，右边 MODEL 是当前文件的变量。
            model=MODEL,
            # [原第 242 行] system=SYSTEM 发送前面定义的系统提示词，说明模型的角色和当前工作目录。
            system=SYSTEM,
            # [原第 243 行] messages=messages 发送目前累积的消息历史，包括用户文字、先前模型响应和工具结果。左右同名，但分别是被调用函数的参数名和当前变量。
            messages=messages,
            # [原第 244 行] tools=TOOLS 把可用工具的名称、说明和参数格式告诉模型。传入它不等于立即执行工具。
            tools=TOOLS,
            # [原第 245 行] max_tokens=8000 设置单次模型响应的生成 token 上限。token 是模型处理文本的单位，不能直接等同于字数；它也不是最大调用轮数。
            max_tokens=8000,
        # [原第 246 行] 关闭 create(...) 调用，取得 SDK 响应对象。网络、认证等错误若在 SDK 处理后仍抛出，此函数没有 try/except 捕获它们。
        )
        # [原第 247 行] 调用之前定义的类方法，从 response 提取文字、工具请求和停止原因，得到 AgentTurn。
        turn = AgentTurn.from_response(response)
        # [原第 248 行] 将当前 turn 保存为 last_turn，供达到轮数上限后的返回逻辑使用。赋值不会自动复制整个对象。
        last_turn = turn

        # [原第 250 行] 注释：先把模型完整响应记入历史，再执行请求的 I/O（输入输出操作，如读写文件、运行命令）。
        # Append the complete assistant turn before executing any requested I/O.
        # [原第 251 行] 把角色为 assistant、内容为完整响应块的字典追加到 messages。即使这一轮只请求工具，也需要记下请求，才能与之后的结果对应。
        messages.append({"role": "assistant", "content": turn.content})

        # [原第 253 行] 注释：没有工具调用的响应将结束本次循环，同时保留具体的停止原因。
        # A turn without tool calls is terminal; the exact reason remains visible.
        # [原第 254 行] 调用 stop_reason_for(turn)，取得 None（继续）或某种停止原因。
        stop_reason = stop_reason_for(turn)
        # [原第 255 行] is not None 检查返回值是否不是 None。is 比较对象身份，这里是 Python 中判断是否缺省的惯用写法。
        if stop_reason is not None:
            # [原第 256 行] 一旦决定停止，就构造 AgentLoopResult 并 return，立即结束整个 agent_loop，而不只是跳出 if。
            return AgentLoopResult(
                # [原第 257 行] 结果的 stop_reason 字段接收刚刚得出的枚举值。
                stop_reason=stop_reason,
                # [原第 258 行] turns 字段记录当前轮号，例如在第 2 次模型响应后结束就记录 2。
                turns=turn_number,
                # [原第 259 行] tool_calls 字段记录前面已产出结果的工具调用总数。当前走的是无工具分支，所以这一轮不会再增加工具计数。
                tool_calls=tool_call_count,
                # [原第 260 行] final_text 使用当前这一轮汇总的文本，不会把历史所有文本再拼成最终答案。
                final_text=turn.text,
                # [原第 261 行] 同时保留本轮服务端原始停止原因，方便调用方区分服务端信息和本地分类。
                provider_stop_reason=turn.provider_stop_reason,
            # [原第 262 行] 结束 AgentLoopResult 构造调用并返回结果。此分支返回后，不会再执行下面的工具列表推导式。
            )

        # [原第 264 行] 注释：执行本轮每一个工具请求，并收集符合接口格式的结果。
        # Execute every tool call from this turn and collect protocol-shaped results.
        # [原第 265 行] 列表推导式：[表达式 for 元素 in 集合]。对 turn.tool_calls 中每项依次调用 execute_bash_call，再把各返回字典组成 results 列表。这是按顺序执行，不是自动并行。
        results = [execute_bash_call(call) for call in turn.tool_calls]
        # [原第 266 行] len(results) 是本轮返回结果的个数；+= 表示在原计数上累加。计数包括参数无效、被拦截和超时后返回的结果，并不只统计成功命令。
        tool_call_count += len(results)

        # [原第 268 行] 注释：把同一轮的工具结果集中放到一条 user 消息里，让下一次模型调用继续。
        # Feed tool results back as one user turn; the next iteration continues.
        # [原第 269 行] 把 results 作为内容追加到 user 角色消息。这里的 user 是 API 协议承载客户端工具结果的角色，并不表示真人又输入了一句话；后续循环会把它交给模型。
        messages.append({"role": "user", "content": results})

    # [原第 271 行] 注释：最后一轮的工具结果仍保留在 messages 中，方便调用者检查。
    # The final tool results stay in messages for inspection, but the harness
    # [原第 272 行] 接上一行：默认到第 8 轮就不再自行请求第 9 轮。若调用者传了其他 max_turns，上限也会相应变化；注释中的 9 仅指默认配置。
    # refuses to start an unbounded ninth turn without an explicit caller choice.
    # [原第 273 行] for 正常耗尽所有轮次且没有提前 return 时，走到这里，返回达到上限的结果。最后一轮里的工具已经执行并回填，但不会额外再请求一次总结。
    return AgentLoopResult(
        # [原第 274 行] 设置停止原因为 LoopStopReason.MAX_TURNS。
        stop_reason=LoopStopReason.MAX_TURNS,
        # [原第 275 行] 记录已经达到的模型轮数上限 max_turns。
        turns=max_turns,
        # [原第 276 行] 记录累计产生结果的工具调用次数，可能大于 max_turns，因为一轮能包含多次工具调用。
        tool_calls=tool_call_count,
        # [原第 277 行] 条件表达式：有 last_turn 时取其 text，否则给空字符串。达到上限时这段文本可能是工具调用前的说明，不一定是完成任务后的答案。
        final_text=last_turn.text if last_turn else "",
        # [原第 278 行] 同样，有最后一轮就保留其 provider_stop_reason，否则记录 None。它可能仍是 tool_use，而本地停止原因已经是 MAX_TURNS，两者描述的层面不同。
        provider_stop_reason=last_turn.provider_stop_reason if last_turn else None,
    # [原第 279 行] 关闭最后这个 AgentLoopResult 构造调用，结束函数定义的主体。
    )


# [原第 282 行] 注释标识程序入口区域，下面负责命令行交互。
# -- Entry point --
# [原第 283 行] 直接运行此文件时，__name__ 等于 '__main__'，才执行下面的交互代码；作为模块 import 时一般不执行此块。但上面的环境配置、客户端创建等顶层代码仍会运行。
if __name__ == "__main__":
    # [原第 284 行] 向终端打印标题 s01: Agent Loop。print 默认在输出末尾加一个换行。
    print("s01: Agent Loop")
    # [原第 285 行] 打印中文使用说明；字符串中的 \n 也是换行，加上 print 默认的换行，会形成额外空行。
    print("输入问题，回车发送。输入 q 退出。\n")

    # [原第 287 行] 创建空的历史消息列表 history，并标注类型为 list[dict[str, Any]]。它位于交互循环外，所以用户接连输入的问题会共用同一份历史。
    history: list[dict[str, Any]] = []
    # [原第 288 行] while True 创建持续运行的交互循环，直到执行 break 或发生未处理异常。这里每一轮接收一个新问题。
    while True:
        # [原第 289 行] 用 try 包住接下来这一条 input 调用，以便处理用户退出输入的情况。
        try:
            # [原第 290 行] input(...) 显示提示符并等待一行输入，返回不含末尾回车的字符串。\033[36m 将提示符设为青色，[0m 恢复颜色；返回值赋给 query。
            query = input("\033[36ms01 >> \033[0m")
        # [原第 291 行] 捕获 EOFError（输入流结束）或 KeyboardInterrupt（通常是 Ctrl+C）。这段 except 只覆盖上方 input，不覆盖后面的 agent_loop 调用。
        except (EOFError, KeyboardInterrupt):
            # [原第 292 行] 输入阶段发生上述异常时，break 跳出最近的 while 循环，结束交互。
            break
        # [原第 293 行] strip() 去掉两端空白，lower() 转小写；in 判断处理后的字符串是否属于元组 ('q', 'exit', '')。因此 Q、带空格的 exit、直接回车和全空格输入都会退出。
        if query.strip().lower() in ("q", "exit", ""):
            # [原第 294 行] 输入匹配退出条件时跳出交互循环，不把这句退出指令提交给模型。
            break

        # [原第 296 行] 把原始 query 作为 user 文字消息追加到 history。前面用于判断退出的 strip()/lower() 没有覆盖 query，因此普通输入中的原始空格和大小写仍保留。
        history.append({"role": "user", "content": query})
        # [原第 297 行] 把 history 传给 agent_loop，等待当前任务的模型与工具循环结束，将其结果保存为 result。函数中的 messages 和这里的 history 指向同一个列表，因此追加的历史会保留到下一次输入。
        result = agent_loop(history)

        # [原第 299 行] 注释：显示返回文本；若循环未按 FINAL_ANSWER 停止，再显示未完整结束的原因。
        # Print the model's final text response, or make an incomplete stop visible.
        # [原第 300 行] 字符串非空时 if 成立，准备显示 final_text。这里检查真假，不检查答案是否准确或任务是否完成。
        if result.final_text:
            # [原第 301 行] 打印这次循环返回的文本。之前带工具请求的轮次文字一般只记在历史里，并未逐轮在终端打印；工具命令及输出由执行函数另行打印。
            print(result.final_text)
        # [原第 302 行] is not 比较停止原因是否不是这个枚举成员。枚举成员可用身份比较；只要是 MAX_TOKENS 或 MAX_TURNS，就进入下一行。
        if result.stop_reason is not LoopStopReason.FINAL_ANSWER:
            # [原第 303 行] 用黄色打印停止提示；result.stop_reason.value 取枚举背后的字符串，如 max_turns。提示后恢复终端颜色。
            print(f"\033[33m[loop stopped: {result.stop_reason.value}]\033[0m")
        # [原第 304 行] 空参数的 print() 输出一个空行，用来分隔这次结果和下一次输入提示。随后回到 while True 的下一轮。
        print()
