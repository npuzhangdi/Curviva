"""P1 拟合报告生成（对标 Origin 的 Fit Report Sheet）。"""

import datetime

from curviva.fitting.engine import FitResult


def _fmt(v, digits: int = 8) -> str:
    try:
        return f"{float(v):.{digits}g}"
    except (TypeError, ValueError):
        return str(v)


def report_text(result: FitResult) -> str:
    """生成可直接复制到论文/实验记录或另存为 .txt/.md 的中文报告。"""
    lines = [
        "# Curviva 拟合报告",
        "",
        f"- 生成时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 模型：{result.name}",
        f"- 表达式（Python）：`{result.expression}`",
        f"- 数据来源：{result.dataset_name or '—'} / X={result.x_column or '—'} / "
        f"Y={result.y_column or '—'}",
        f"- 权重：{result.weight_mode}",
        f"- 状态：{result.message}",
        "",
        "## 拟合参数",
        "",
        "| 参数 | 估计值 | 标准误 | 相对误差 |",
        "|---|---:|---:|---:|",
    ]
    for name, value in result.params.items():
        se = result.stderr.get(name, float("nan"))
        rel = abs(se / value) * 100 if value else float("nan")
        lines.append(f"| {name} | {_fmt(value)} | {_fmt(se)} | {_fmt(rel, 4)} % |")

    s = result.stats
    lines += [
        "",
        "## 拟合优度",
        "",
        "| 指标 | 数值 |",
        "|---|---:|",
        f"| 数据点数 N | {s.get('n', '—')} |",
        f"| 参数个数 k | {s.get('k', '—')} |",
        f"| R² (COD) | {_fmt(s.get('r2'), 8)} |",
        f"| 调整 R² | {_fmt(s.get('adj_r2'), 8)} |",
        f"| RMSE | {_fmt(s.get('rmse'), 8)} |",
        f"| 约化 χ² | {_fmt(s.get('reduced_chi2'), 8)} |",
        f"| 残差平方和 RSS | {_fmt(s.get('rss'), 8)} |",
        f"| AIC | {_fmt(s.get('aic'), 8)} |",
        f"| 迭代次数 | {result.iterations} |",
        "",
        "## 说明",
        "",
        "- 标准误由 χ²·(JᵀJ)⁻¹ 协方差矩阵对角元开方得到；95% 置信带为 ±1.96·SE。",
        "- 引擎为纯 numpy 实现的 Levenberg–Marquardt 加权最小二乘，未依赖 scipy。",
        "- 扩展模型只允许 Python 表达式；`x` 为自变量，其余自由变量为待拟合参数。",
        "",
    ]
    return "\n".join(lines)


def parameter_table(result: FitResult) -> list:
    """供界面表格显示：[(参数名, 值, 标准误)]。"""
    return [(k, _fmt(v), _fmt(result.stderr.get(k)))
            for k, v in result.params.items()]


def statistic_table(result: FitResult) -> list:
    labels = [("数据点数 N", "n"), ("参数个数 k", "k"), ("R²", "r2"),
              ("调整 R²", "adj_r2"), ("RMSE", "rmse"),
              ("约化 χ²", "reduced_chi2"), ("AIC", "aic")]
    return [(label, _fmt(result.stats.get(key))) for label, key in labels]
