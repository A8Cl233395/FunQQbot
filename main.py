from user_functions import *

# 陷阱：
# - 必须在仓库根目录启动；配置与 data 路径都是相对路径。
# - 退出顺序固定：取消 Sync 任务并落盘 -> 保存各群/用户状态 -> os._exit(0)；强停不会执行保存。

async def main():
    server = await websockets.serve(handler, "0.0.0.0", 8080)
    sync = asyncio.create_task(Sync.connect())
    logger.info("WebSocket服务器已在 ws://0.0.0.0:8080 启动，等待连接...")
    try:
        await asyncio.Future()  
    finally:
        logger.info("正在关闭服务器...")
        server.close()
        sync.cancel()
        Sync.save()
        logger.info("服务器已关闭。")
        logger.info("正在保存所有用户和群的状态...")
        for group_id in groups:
            await groups[group_id].on_quit()
            logger.debug("Done Saving Group %s", group_id)
        for user_id in users:
            await users[user_id].on_quit()
            logger.debug("Done Saving User %s", user_id)
        logger.info("保存完成。")
        os._exit(0)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("检测到手动中断，程序退出。")