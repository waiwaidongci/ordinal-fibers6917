"""持续监测：对全部工艺对反复查看有序等级的优胜证据，整族误报由α约束。

设计要点（与固定样本 RankTestRun 完全分开，不复用也不改写其结果）：

* 试样按入库顺序（reading.id）在各工艺内排列；工艺对 (i,j) 只使用两组共同前缀
  min(n_i, n_j) 份试样，第 r 份对第 r 份，每份试样在同一组对中只出现一次。
  多出来的试样原样列出，等待配齐，不参与该组对的证据。
* 组对效应按“并列计半”报告：theta = (W + T/2) / m，即 P(左等级更高) +
  0.5·P(并列)。证据本身用精确符号检验（W 对 L，并列不计方向），条件在非并列
  份数上服从 Binomial(n, 1/2)，不依赖正态渐近。
* 查看次数 k 在监测开始时即计入预算：第 k 回、m 个组对中，每个组对可花
  alpha·6/(pi^2 k^2 m)，全部查看、全部组对求和恰为 alpha。于是无论团队查看
  多少次、在何时停看，整族至少一次误报的概率不超过 alpha；不预设总批数。
  可依据已有结果调整后续取样，因为该保证覆盖任意前缀与任意停看时刻。
* 证据只由（锁定的工艺与alpha、按id排序的读数、查看序号）决定；同一输入
  完整重放得到逐字节相同的规范化证据。源数据指纹变化会使旧证据失效并重算。
"""
import hashlib
import json
import math
from itertools import combinations

ALGORITHM = 'ordinal-pair-prefix-sign-spending-v1'
GRADE_MIN = 1
GRADE_MAX = 9
MAX_SPECIMENS = 2000
SPENDING_TAIL = 6.0 / math.pi ** 2  # sum_{k>=1} 6/(pi^2 k^2) = 1


# ---------------------------------------------------------------- incomplete beta
def _betacf(a, b, x):
    """Continued fraction for the incomplete beta function (Numerical Recipes)."""
    max_iter, eps, fpmin = 300, 3e-14, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < fpmin:
        d = fpmin
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def _betainc(a, b, x):
    """Regularized incomplete beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    log_beta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(a * math.log(x) + b * math.log1p(-x) - log_beta)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - math.exp(b * math.log1p(-x) + a * math.log(x) - log_beta) * _betacf(b, a, 1.0 - x) / b


def sign_test_p(wins, losses):
    """精确双侧符号检验：H0 下非并列方向各半，并列不提供方向。"""
    n = wins + losses
    if n <= 0:
        return 1.0
    tail = _betainc(float(max(wins, losses)), float(n - max(wins, losses) + 1), 0.5)
    return min(1.0, 2.0 * tail)


# ---------------------------------------------------------------- alpha spending
def validate_alpha(alpha):
    if isinstance(alpha, bool) or not isinstance(alpha, (int, float)):
        raise ValueError('alpha须为数值')
    alpha = float(alpha)
    if not math.isfinite(alpha) or not 0.0 < alpha < 1.0:
        raise ValueError('alpha须在0与1之间')
    return alpha


def look_spending(look_index, family_size):
    """第 look_index 回查看中，每一个组对可分得的整族误报预算（占 alpha 的比例）。"""
    if look_index < 1 or family_size < 1:
        raise ValueError('查看序号与组对数必须为正')
    return SPENDING_TAIL / (family_size * look_index ** 2)


def anytime_p(p_value, look_index, family_size):
    """把第 k 回的原始精确 p 换成整族随时可停看的 p（与 alpha 直接比较）。"""
    return min(1.0, p_value / look_spending(look_index, family_size))


# ---------------------------------------------------------------- evidence
def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def readings_fingerprint(readings):
    """只覆盖锁定工艺的当前读数；按（工艺id，试样编号）规范排序。"""
    rows = [[int(r['id']), int(r['treatment_id']), r['specimen_code'], float(r['grade'])]
            for r in readings]
    rows.sort(key=lambda r: (r[1], r[2], r[0]))
    return hashlib.sha256(canonical_json({'algorithm': ALGORITHM, 'readings': rows}).encode()).hexdigest()


def plan_fingerprint(study, treatments, alpha, look_rule):
    plan = {'algorithm': ALGORITHM,
            'study': {k: study[k] for k in ('id', 'code', 'name')},
            'treatments': [{'id': t['id'], 'code': t['code'], 'name': t['name']} for t in treatments],
            'alpha': float(alpha), 'look_rule': look_rule}
    return hashlib.sha256(canonical_json(plan).encode()).hexdigest()


def _sorted_groups(treatments, readings):
    by_id = {t['id']: [] for t in treatments}
    for r in readings:
        if r['treatment_id'] in by_id:
            by_id[r['treatment_id']].append(r)
    groups = []
    for t in treatments:
        rows = sorted(by_id[t['id']], key=lambda r: (int(r['id']), r['specimen_code']))
        groups.append({'treatment': t, 'rows': rows})
    return groups


def build_evidence(plan, readings, look_index, excluded=0, planned_total=None):
    """由锁定计划与读数前缀直接计算证据；纯函数，不含时间戳，可逐字节重放。

    excluded 只记录研究里读取到、但不属于锁定工艺的读数份数，用于审计；
    它们既不配对也不进入任何组对的证据。planned_total 是可选的锁定制备总量，
    只用于显示“还差多少份”，不改变任何统计量。
    """
    alpha = validate_alpha(plan['alpha'])
    treatments = sorted(plan['treatments'], key=lambda t: (t['code'], t['id']))
    if not 2 <= len(treatments) <= 5:
        raise ValueError('监测须锁定2–5个预定义工艺')
    if len({t['id'] for t in treatments}) != len(treatments):
        raise ValueError('锁定工艺标识重复')
    ids = {t['id'] for t in treatments}
    for r in readings:
        if r['treatment_id'] not in ids:
            raise ValueError('读数引用了监测之外的工艺')
        x = r['grade']
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(float(x)):
            raise ValueError('形成等级必须为1–9整数')
        if not GRADE_MIN <= float(x) <= GRADE_MAX or int(x) != x:
            raise ValueError('形成等级必须为1–9整数，非等距性能量')
    if len(readings) > MAX_SPECIMENS:
        raise ValueError('最多2000份独立试样')
    if len({r['specimen_code'] for r in readings}) != len(readings):
        raise ValueError('试样标识重复，不能当作独立试样')

    groups = _sorted_groups(treatments, readings)
    family_size = len(treatments) * (len(treatments) - 1) // 2
    share = look_spending(look_index, family_size)
    pairs = []
    for i, j in combinations(range(len(groups)), 2):
        left, right = groups[i], groups[j]
        m = min(len(left['rows']), len(right['rows']))
        wins = losses = ties = 0
        for a, b in zip(left['rows'][:m], right['rows'][:m]):
            if a['grade'] > b['grade']:
                wins += 1
            elif a['grade'] < b['grade']:
                losses += 1
            else:
                ties += 1
        theta = (wins + 0.5 * ties) / m if m else None
        psi = (wins - losses) / m if m else None
        p_exact = sign_test_p(wins, losses)
        p_anytime = anytime_p(p_exact, look_index, family_size)
        direction = 'left' if wins > losses else 'right' if losses > wins else 'none'
        left_waiting = [r['specimen_code'] for r in left['rows'][m:]]
        right_waiting = [r['specimen_code'] for r in right['rows'][m:]]
        pairs.append({
            'i': i, 'j': j,
            'left_id': left['treatment']['id'], 'left_code': left['treatment']['code'],
            'left_name': left['treatment']['name'],
            'right_id': right['treatment']['id'], 'right_code': right['treatment']['code'],
            'right_name': right['treatment']['name'],
            'paired': m, 'win_left': wins, 'loss_left': losses, 'ties': ties,
            'theta_left_higher_half_ties': theta,
            'psi_left_minus_right': psi,
            'tie_share': ties / m if m else None,
            'direction': direction,
            'p_exact_sign': p_exact,
            'p_anytime': p_anytime,
            'reject': bool(p_anytime <= alpha),
            'waiting_left': left_waiting, 'waiting_right': right_waiting,
            'waiting_left_count': len(left_waiting), 'waiting_right_count': len(right_waiting),
        })
    family_p = min((p['p_anytime'] for p in pairs), default=1.0)
    balanced = len({len(g['rows']) for g in groups}) == 1
    smallest = min(len(g['rows']) for g in groups)
    waiting_by_group = [{'id': g['treatment']['id'], 'code': g['treatment']['code'],
                         'name': g['treatment']['name'], 'n': len(g['rows']),
                         'waiting': [r['specimen_code'] for r in g['rows'][smallest:]]}
                        for g in groups]
    return {
        'algorithm': ALGORITHM,
        'look_index': look_index,
        'planned_total': planned_total,
        'alpha': alpha,
        'family_size': family_size,
        'spending_share': share,
        'spending_tail_constant': SPENDING_TAIL,
        'specimen_counts': [{'id': g['treatment']['id'], 'code': g['treatment']['code'],
                             'name': g['treatment']['name'], 'n': len(g['rows'])}
                            for g in groups],
        'total_specimens': sum(len(g['rows']) for g in groups),
        'excluded_reading_count': int(excluded),
        'balanced_prefix': balanced,
        'waiting_by_group': waiting_by_group,
        'paired_specimens_per_pair': [p['paired'] for p in pairs],
        'family_p': family_p,
        'decisive': bool(family_p <= alpha),
        'pairs': pairs,
        'input_fingerprint': readings_fingerprint(readings),
        'plan_fingerprint': plan_fingerprint(plan['study'], treatments, alpha, plan['look_rule']),
        'scope': ('同一组对内每份试样只使用一次；并列计半仅用于theta，证据用精确符号检验；'
                  '整族误报由查看次数spending约束；不作工艺因果或性能概率'),
    }


def prefix_trace(plan, readings, pair_key, step=1):
    """追查一个组对的前缀证据：第 r 份配齐时的 W/L/T、theta 与原始符号p。"""
    if step < 1:
        raise ValueError('步长须为正整数')
    treatments = sorted(plan['treatments'], key=lambda t: (t['code'], t['id']))
    groups = _sorted_groups(treatments, readings)
    index = {t['id']: n for n, t in enumerate(treatments)}
    try:
        i_text, j_text = str(pair_key).split('-')
        i, j = index[int(i_text)], index[int(j_text)]
    except Exception:
        raise ValueError('请以左工艺id-右工艺id指定组对')
    if i == j:
        raise ValueError('组对须为两个不同工艺')
    if i > j:
        i, j = j, i
    left, right = groups[i], groups[j]
    m = min(len(left['rows']), len(right['rows']))
    rows, wins = [], 0
    losses = ties = 0
    for r in range(1, m + 1):
        a, b = left['rows'][r - 1], right['rows'][r - 1]
        if a['grade'] > b['grade']:
            wins += 1
        elif a['grade'] < b['grade']:
            losses += 1
        else:
            ties += 1
        if r % step == 0 or r == m:
            rows.append({'r': r, 'win_left': wins, 'loss_left': losses, 'ties': ties,
                         'theta_left_higher_half_ties': (wins + 0.5 * ties) / r,
                         'psi_left_minus_right': (wins - losses) / r,
                         'p_exact_sign': sign_test_p(wins, losses)})
    return {
        'left_code': left['treatment']['code'], 'left_name': left['treatment']['name'],
        'right_code': right['treatment']['code'], 'right_name': right['treatment']['name'],
        'paired': m,
        'paired_left': [{'id': r['id'], 'specimen_code': r['specimen_code'], 'grade': r['grade']}
                        for r in left['rows'][:m]],
        'paired_right': [{'id': r['id'], 'specimen_code': r['specimen_code'], 'grade': r['grade']}
                         for r in right['rows'][:m]],
        'waiting_left': [{'id': r['id'], 'specimen_code': r['specimen_code'], 'grade': r['grade']}
                         for r in left['rows'][m:]],
        'waiting_right': [{'id': r['id'], 'specimen_code': r['specimen_code'], 'grade': r['grade']}
                          for r in right['rows'][m:]],
        'prefix': rows,
        'step': step,
    }
