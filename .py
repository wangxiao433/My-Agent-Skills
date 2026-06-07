import os
import glob
import json
import urllib.request
from datetime import datetime, timezone, timedelta

def gather_daily_project_context(github_username: str, workspace_path: str) -> str:
    """
    【Skill 描述】: 
    全量捕获用户当天的工作上下文。自动抓取线上的 GitHub 产出痕迹，
    并同步扫描本地工作空间（如 Ansys、MuJoCo 等仿真工程）中的底层运行日志，
    最终合并为结构化的数据包返回。
    
    【AI 调用与处理说明】:
    当 AI 成功调用此函数并拿到返回的字符串后，必须严格执行以下任务：
    1. 交叉对比数据：将用户的代码提交与本地仿真日志（如 NaN 报错或 OOM）结合起来分析。
    2. 输出【今日复盘档案】：
       - 必须标注整理日期（精确到年月日）。
       - 逐项列出【做了什么】与【遇到了什么底层问题/背景】。
       - 明确输出【缺漏与下一步待办提醒】。
    """
    
    # 统一时区：获取本地东八区（UTC+8）的时间边界
    tz_utc_8 = timezone(timedelta(hours=8))
    now_local = datetime.now(tz_utc_8)
    today_str = now_local.strftime("%Y-%m-%d")
    time_boundary = now_local - timedelta(days=1) # 扫描过去 24 小时的本地文件
    
    final_context_report = f"📅 数据捕获日期: {today_str}\n"
    final_context_report += "="*50 + "\n"
    
    # =====================================================================
    # 模块 1：抓取线上 GitHub 活动轨迹
    # =====================================================================
    final_context_report += "【线上工程产出 (GitHub)】\n"
    github_url = f"https://api.github.com/users/{github_username}/events"
    req = urllib.request.Request(github_url, headers={"User-Agent": "Local-Agent-Skill"})
    
    github_logs = []
    try:
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                events = json.loads(response.read().decode('utf-8'))
                for event in events:
                    # 转换 GitHub 的 UTC 时间为东八区时间
                    created_at_utc = datetime.strptime(event["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                    event_date_str = created_at_utc.astimezone(tz_utc_8).strftime("%Y-%m-%d")
                    
                    if event_date_str == today_str:
                        repo_name = event["repo"]["name"]
                        event_type = event["type"]
                        
                        if event_type == "PushEvent":
                            for commit in event["payload"].get("commits", []):
                                github_logs.append(f"- [代码提交] 仓库: {repo_name} | 信息: {commit.get('message', '')}")
                        elif event_type == "IssuesEvent":
                            action = event["payload"].get("action", "")
                            issue_title = event["payload"].get("issue", {}).get("title", "")
                            github_logs.append(f"- [任务管理] 仓库: {repo_name} | 操作: {action} | 标题: {issue_title}")
    except Exception as e:
        github_logs.append(f"获取 GitHub 数据失败: {str(e)}")
        
    if not github_logs:
        final_context_report += "今日无公开的 GitHub 活动痕迹。\n"
    else:
        final_context_report += "\n".join(github_logs) + "\n"

    final_context_report += "\n" + "="*50 + "\n"

    # =====================================================================
    # 模块 2：扫描本地仿真与系统运行日志
    # =====================================================================
    final_context_report += f"【本地仿真调试盲区数据 (路径: {workspace_path})】\n"
    
    if not os.path.exists(workspace_path):
        final_context_report += f"警告：找不到指定的本地工作目录 {workspace_path}，无法分析本地报错。\n"
    else:
        log_extensions = ['*.log', '*.txt', '*.out', '*.err']
        file_list = []
        
        # 递归扫描包含关键字的日志文件
        for ext in log_extensions:
            search_pattern = os.path.join(workspace_path, '**', ext)
            for file_path in glob.glob(search_pattern, recursive=True):
                try:
                    mod_time = datetime.fromtimestamp(os.path.getmtime(file_path)).astimezone(tz_utc_8)
                    if mod_time > time_boundary:
                        file_list.append((file_path, mod_time))
                except Exception:
                    continue

        if not file_list:
            final_context_report += "过去 24 小时内未检测到任何本地日志文件的更新。\n"
        else:
            # 提取日志中的高价值报错与状态信息
            keywords = ['error', 'warning', 'failed', 'converge', 'nan', 'divergence', 'fatal', 'exception', 'timeout']
            
            for file_path, mod_time in file_list:
                file_name = os.path.basename(file_path)
                final_context_report += f"\n--- 📄 文件: {file_name} ({mod_time.strftime('%H:%M:%S')}) ---\n"
                
                critical_lines = []
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                        if len(lines) < 50:
                            critical_lines = [line.strip() for line in lines if line.strip()]
                        else:
                            for line_num, line in enumerate(lines, 1):
                                if any(kw in line.lower() for kw in keywords):
                                    critical_lines.append(f"[Line {line_num}] {line.strip()}")
                                    
                        if critical_lines:
                            final_context_report += "\n".join(critical_lines[:50]) + "\n" # 截断保护，防止 token 超载
                        else:
                            final_context_report += "（日志已更新，但未捕获到明显的错误或收敛警告）\n"
                except Exception as e:
                    final_context_report += f"读取失败: {str(e)}\n"

    # =====================================================================
    # 最终指令：要求本地 AI 开始思考
    # =====================================================================
    final_context_report += "\n" + "="*50 + "\n"
    final_context_report += "【系统指令】：数据收集完毕。请本地 AI 立即阅读上方所有数据，并为用户生成包含成就、深度问题剖析以及待办提醒的专业周/日报。"
    
    return final_context_report

# =====================================================================
# 本地测试桩 (仅用于你手工调试查看效果，AI 调用时不会触发此处)
# =====================================================================
if __name__ == "__main__":
    # 请在这里填入你真实的 GitHub 用户名和你平时存放工程代码/仿真文件的根目录
    TEST_USERNAME = "你的GitHub用户名" 
    TEST_WORKSPACE = r"C:\Your\Project\Workspace" 
    
    print("正在测试执行统一数据捕获 Skill...")
    result_data = gather_daily_project_context(TEST_USERNAME, TEST_WORKSPACE)
    print("\n" + result_data)