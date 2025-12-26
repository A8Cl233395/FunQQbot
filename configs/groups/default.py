from typing import TYPE_CHECKING

# 这一块只在 IDE 类型检查时运行，实际运行时不会循环导入
if TYPE_CHECKING:
    from main import Handle_group_message

def hook_init(self: "Handle_group_message"):
    # self.config # 当前群组配置 dict
    pass

def hook_process(self: "Handle_group_message"):
    # messages # 全部信息 dict
    # plain_text # 转换为文本后的消息，不包含名字 str
    # text # 转换为文本后的消息，包含名字 str
    # is_mentioned # 是否被 @ bool
    # message_send # 要发送的消息 list
    pass