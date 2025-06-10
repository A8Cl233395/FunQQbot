# {"init": true, "plugin_data": []}
# 第一行注释会被加载，以下为可用样例
# {"init": true, "plugin_data": "HELLO"}
# {"init": true} # 默认为None
# {"init": false} # 只在更新不删除数据时使用

print(self.plugin_data)
print(self.original_messages)
print(sender_id)
print(plain_text)