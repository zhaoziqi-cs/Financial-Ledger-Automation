# Financial Ledger Automation

自动化更新资金台账系统。

## 功能

- 银行流水自动解析
- 项目自动识别
- 自动更新资金台账
- 更新数据库结构存储结果

## 使用流程

1 初始化 ledger
2 导入银行流水
3 运行 pipeline

## 网页版使用（待更新）

1 安装依赖

```bash
pip install -r requirements.txt
```

2 启动网页服务

```bash
python app.py
```

3 打开浏览器访问

```text
http://127.0.0.1:5000
```

4 上传两个文件

- 银行日记账（台账文件）
- 银行流水