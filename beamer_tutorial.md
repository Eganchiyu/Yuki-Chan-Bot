# 用 LaTeX beamer 做 PPT —— 最简入门教程

> 配套模板文件：`beamer_minimal_template.tex`
> 编译引擎：**XeLaTeX**（不要用 pdfLaTeX）

---

## 0. 最小可运行示例

```latex
\documentclass[aspectratio=169, 11pt]{beamer}
\usepackage{ctex}          % 中文支持，必须
\usepackage{graphicx}      % 插图

\usetheme{Madrid}
\usecolortheme{default}

\title{标题}
\author{作者}
\date{\today}

\begin{document}
\begin{frame}
    \titlepage
\end{frame}

\begin{frame}{目录}
    \tableofcontents
\end{frame}

\section{第一节}

\begin{frame}{我的第一页}
    \begin{itemize}
        \item 要点一
        \item 要点二
    \end{itemize}
\end{frame}

\end{document}
```

编译命令（命令行）：

```bash
xelatex beamer_minimal_template.tex
```

或使用 `latexmk`（推荐，自动跑两遍生成目录）：

```bash
latexmk -xelatex beamer_minimal_template.tex
```

---

## 1. 常用命令速查

| 需求 | 命令 | 说明 |
| --- | --- | --- |
| 分节（自动进目录） | `\section{名称}` | 配合 `\tableofcontents` 生成目录；建议每节第一页用 `\sectionpage`（metropolis 主题） |
| 新建一页 | `\begin{frame} ... \end{frame}` | 一页 PPT = 一个 frame |
| 页面标题 | `\frametitle{标题}` | 或简写 `\begin{frame}{标题} ... \end{frame}` |
| 无序列表 | `\begin{itemize} \item xxx \end{itemize}` | 有序列表用 `enumerate` |
| 分栏 | `\begin{columns}[T] \begin{column}{0.48\textwidth} ... \end{column} \end{columns}` | 两栏宽度之和不要超过 1.0 |
| 高亮块 | `\begin{block}{标题} ... \end{block}` | 同类还有 `alertblock`（红色警告）、`exampleblock`（绿色示例） |
| 分步动画 | `\pause` | 放在两句之间，放映时点击后才显示后面的内容 |
| 覆盖式动画 | `\item<1->`、`\only<2>{...}`、`\onslide<3->{...}` | 更精细的分步控制 |
| 插图 | `\includegraphics[width=0.6\textwidth]{图片.png}` | 需 `\usepackage{graphicx}`；建议放进 `figure` 环境加 `\caption` |
| 居中 | `\centering`（在 frame 内） | 也可以用 `center` 环境 |
| 换行 | `\\` | 换段用空行 |
| 注释 | `% 这一行不编译` | 转义百分号写 `\%` |

### 示例：分栏 + 高亮块

```latex
\begin{frame}{分栏演示}
    \begin{columns}[T]
        \begin{column}{0.48\textwidth}
            \begin{block}{左栏}
                \begin{itemize}
                    \item 要点一
                    \item 要点二
                \end{itemize}
            \end{block}
        \end{column}
        \begin{column}{0.48\textwidth}
            \begin{alertblock}{右栏}
                这里是强调内容。
            \end{alertblock}
        \end{column}
    \end{columns}
\end{frame}
```

### 示例：插图

```latex
\begin{frame}{插图}
    \begin{figure}
        \centering
        \includegraphics[width=0.6\textwidth]{example.png}
        \caption{图片标题}
    \end{figure}
\end{frame}
```

---

## 2. 推荐主题与配色

### 好看的主题（`\usetheme{...}`）

| 主题 | 特点 | 备注 |
| --- | --- | --- |
| `metropolis` | 极简现代、扁平化，学术报告首选 | **需单独安装** `beamertheme-metropolis`，编译仍用 XeLaTeX，推荐搭配 Fira 字体 |
| `Madrid` | 经典蓝色，带底部导航条 | 开箱即用，稳 |
| `Warsaw` | 与 Madrid 类似，顶部圆点导航 | 开箱即用 |
| `Berlin` | 顶部分节进度条 | 适合章节清晰的汇报 |
| `CambridgeUS` | 学术风、配色沉稳 | 开箱即用 |
| `Frankfurt` | 简洁，带 mini frame 导航 | 开箱即用 |
| `PaloAlto` / `Berkeley` | 侧边栏目录 | 信息量大时好用 |

### 换配色（`\usecolortheme{...}`）

```latex
\usetheme{Madrid}
\usecolortheme{beaver}      % 可选：default / whale / dolphin / seahorse / beetle / crane / dove / beaver ...
```

### 自定义主色（最实用）

```latex
\usepackage{xcolor}
\definecolor{mainblue}{RGB}{0, 82, 155}
\usecolortheme[named=mainblue]{structure}   % 把整体主色调改成 mainblue
```

常用色名速查：`default`、`whale`（深蓝）、`dolphin`（蓝灰）、`seahorse`（浅蓝）、`beetle`（灰）、`crane`（橙黄）、`dove`（灰白）。

---

## 3. 常见踩坑提醒

1. **必须用 XeLaTeX 编译，不要用 pdfLaTeX**
   - 中文（ctex）在 pdfLaTeX 下会报错或乱码。
   - 命令行：`xelatex xxx.tex`；VS Code 里把 `latex-workshop.latex.recipes` 换成 xelatex 配方。

2. **中文一定要加 `\usepackage{ctex}`**
   - 放在 `\documentclass` 之后。
   - ctex 会自动处理中文字体和行距，不要再手动 `\usepackage{xeCJK}` 重复加载。

3. **标题 / 正文里的特殊字符要转义**
   - 常见需转义字符：`# $ % & _ { } ~ ^ \`
   - 转义写法：`\#` `\$` `\%` `\&` `\_` `\{` `\}` `\textasciitilde{}` `\textasciicircum{}` `\textbackslash{}`
   - 例如 `\section{C\_\+\+ 入门}` 里下划线必须写成 `\_`，否则编译报错。
   - 想在标题里写反斜杠命令用 `\texttt{\textbackslash pause}`。

4. **换行用 `\\`，不要用 `\newline` 硬凑**
   - 段内换行：`第一行 \\ 第二行`
   - 换段落：直接空一行（不要写 `\\` 后面接空行，容易报 `There's no line here to end`）。

5. **每页内容不要塞太满**
   - 一页 frame 建议 5~7 个 `\item` 以内；超出请拆页，否则会出现 `Overfull \vbox` 警告、内容溢出屏幕。

6. **`\pause` 与 `\item<...>` 不要混用在同一处**
   - 二者都是覆盖动画，混用会导致步数错乱，选一种即可。

7. **目录要编译两遍**
   - 有 `\tableofcontents` / `\section` 时，至少编译两次（或用 `latexmk`）目录才完整。

8. **图片路径与格式**
   - XeLaTeX 支持 png / jpg / pdf，不直接支持 svg（先用 inkscape 转 pdf）。
   - 文件名不要用中文和空格，避免找图失败。

9. **换行符与编码**
   - 文件保存为 **UTF-8（无 BOM）**，否则 XeLaTeX 可能报错。

10. **`metropolis` 主题报错找不到**
    - 需额外安装：TeX Live 用户 `tlmgr install beamertheme-metropolis`；
    - 或改用内置的 `Madrid` / `Warsaw` / `Berlin`，效果也很稳。

---

## 4. 推荐工作流

```bash
# 1) 复制模板
cp beamer_minimal_template.tex mytalk.tex

# 2) 编辑后编译（自动跑两遍生成目录）
latexmk -xelatex mytalk.tex

# 3) 产物
# mytalk.pdf   直接拿去当 PPT 放映
```

放映提示：PDF 用 Adobe Acrobat / Okular / evince 全屏播放，beamer 的 `\pause` 分步动画在放映时点击生效。
