# reprotrace

**把一次不可复现的结果写成可重跑的档案。**

`reprotrace` —— 记录提示词、参数、输入与环境快照，让同一次生成能被再次跑出来。

- 零依赖，Python 3.10+ 标准库即可运行
- 单文件，`reprotrace.py` 拷走就能用
- 不联网、不写文件

<!-- ipos:install -->
## 安装

零依赖，Python 3.10+ 即可：

```bash
pip install janvangen-reprotrace
```

装完直接用命令名调用：

```bash
reprotrace --help
```

也可以不用安装，直接把 `reprotrace.py` 拷走用——它只依赖标准库。

## 为什么需要它

复现工具多只记参数；reprotrace 连环境与模型版本一起快照，明确标注哪部分不可控。

它遵守下面几条自己定的规矩：

1. **跑不出来等于没发生**。所以档案要包含跑起来所需的一切。
2. **诚实标注不可控的部分**。模型权重会变、服务端会改，这些本来就不可能完全复现，与其假装能做到，不如标出来。
3. **只记录，不重跑**。这个工具不发起任何模型调用。

## 用法

```bash
python reprotrace.py --capture run.json --out archive.json
python reprotrace.py --capture run.json --out archive.json --verify archive.json
```

加 `--json` 可以拿到机器可读的结果，便于接到流水线里。

## 已知局限

- 服务端权重变更这类外部因素无法复现，档案里只标注不掩盖。
- 只记录不重跑，不会发起任何模型调用。
- 输入输出只存哈希，不存原文——想比对原文得自己另外留档。

## 跑测试

```bash
python test_reprotrace.py
```

测试用独立的断言与临时数据，不污染工作目录。

## 来源与参考

- Python 标准库文档：<https://docs.python.org/3/>
- GitHub 仓库：<https://github.com/janvangen/reprotrace>

---

## 关于作者

janvangen 做生成结果的可复现性相关的问题。这个工具先替你回答一个具体问题，再谈别的。

- 个人主页：<https://janvangen.github.io>
- 仓库：<https://github.com/janvangen/reprotrace>

## 许可

MIT，见 [LICENSE](LICENSE)。
