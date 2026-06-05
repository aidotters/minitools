---
name: acceptance-test
description: 受け入れ条件の検証
user-invocable: true
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
argument-hint: "[.steeringパス], --from-idea [ファイル名]"
---

# 受け入れテスト

**目的:** requirements.mdまたはアイデアファイルの受け入れ条件を1つずつ検証し、合否を判定します。

**引数:**
- `/acceptance-test [.steeringパス]` - 指定したsteeringディレクトリの受け入れ条件を検証
- `/acceptance-test --from-idea [ファイル名]` - 指定したアイデアファイルの受け入れ条件を検証
- `/acceptance-test --from-idea` - 最新のアイデアファイルの受け入れ条件を検証
- `/acceptance-test` - 最新のsteeringディレクトリを自動検出して検証

---

## ステップ1: 受け入れ条件の抽出

### 1.1 ソースの特定

```
# .steeringパス指定時
Read('[指定パス]/requirements.md')

# --from-idea指定時
Read('docs/ideas/[指定ファイル].md')

# 引数なし時
Bash('ls -t .steering/ | head -1')
→ 最新のsteeringディレクトリを使用
Read('.steering/[最新]/requirements.md')
```

### 1.2 条件の抽出

「受け入れ条件」セクションから全条件を抽出:

```markdown
## 受け入れ条件

### 機能1
- [ ] 条件1-1
- [ ] 条件1-2

### 機能2
- [ ] 条件2-1
```

→ リスト化:
1. 条件1-1（機能1）
2. 条件1-2（機能1）
3. 条件2-1（機能2）

---

## ステップ2: 条件の分類

各条件を検証方法で分類します。

### 分類基準

| カテゴリ | 説明 | 検証方法 |
|----------|------|----------|
| CODE_EXISTS | クラス/関数の存在 | Grep検索 |
| BEHAVIOR | 動作の確認 | テスト実行 |
| CONFIG | 設定項目の存在 | ファイル検索 |
| INTEGRATION | 外部連携 | 手動確認 |
| UX | ユーザー体験 | 手動確認 |
| PERFORMANCE | パフォーマンス | ベンチマーク/手動確認 |

### 分類の実行

```python
# 擬似コード
for 条件 in 受け入れ条件:
    if "クラス" in 条件 or "関数" in 条件 or "実装" in 条件:
        カテゴリ = CODE_EXISTS
    elif "動作" in 条件 or "できる" in 条件:
        カテゴリ = BEHAVIOR
    elif "設定" in 条件 or "オプション" in 条件:
        カテゴリ = CONFIG
    elif "連携" in 条件 or "API" in 条件:
        カテゴリ = INTEGRATION
    else:
        カテゴリ = UX  # デフォルト: 手動確認
```

---

## ステップ3: 自動検証の実行

`Skill('validation')`を使用して自動検証可能な条件を検証します。

### 3.1 CODE_EXISTS カテゴリ

```
# 例: 「XxxAnalyzerクラスが実装されている」
Grep('class XxxAnalyzer', 'src/')
→ 見つかれば PASS、なければ FAIL
```

### 3.2 CONFIG カテゴリ

```
# 例: 「.envにXXX項目がある」または「src/config.pyに設定がある」
Grep('XXX=', '.env')  # または src/config.py 内の設定を検索
→ 見つかれば PASS、なければ FAIL
```

### 3.3 BEHAVIOR カテゴリ

```bash
# 対応するテストがあれば実行
Bash('pytest tests/test_xxx.py -v')
→ テストパスすれば PASS、失敗すれば FAIL
```

### 検証ルール

| 条件パターン | 検証方法 |
|--------------|----------|
| 「〜クラスが存在する」 | `Grep('class {クラス名}', ...)` |
| 「〜関数が実装されている」 | `Grep('def {関数名}', ...)` |
| 「〜設定項目がある」 | `Grep('{設定キー}:', 'settings.yaml')` |
| 「〜ファイルが作成される」 | `Glob('{ファイルパターン}')` |
| 「〜エラーが処理される」 | `Grep('except|try:', ...)` |
| 「〜ログが出力される」 | `Grep('logger\.|logging\.', ...)` |

---

## ステップ4: 手動確認チェックリストの生成

自動検証できない条件については、手動確認用のチェックリストを生成します。

### 対象カテゴリ

- INTEGRATION: 外部サービスとの連携確認
- UX: ユーザー体験の確認
- PERFORMANCE: パフォーマンス計測

### チェックリスト形式

```markdown
## 手動確認チェックリスト

### 外部連携
- [ ] **条件**: Slack通知が正しく送信される
  - **確認手順**:
    1. テスト用Slack Webhookを設定
    2. `python -m minitools-xxx --slack` を実行
    3. Slackチャンネルで通知を確認
  - **期待結果**: 通知が届き、フォーマットが正しい

### ユーザー体験
- [ ] **条件**: エラー時に分かりやすいメッセージが表示される
  - **確認手順**:
    1. 無効な引数でコマンドを実行
    2. エラーメッセージを確認
  - **期待結果**: 何が問題でどう対処すべきかが分かる

### パフォーマンス
- [ ] **条件**: 100件の記事を3分以内に処理できる
  - **確認手順**:
    1. `time python -m minitools-xxx --max-results 100` を実行
    2. 実行時間を確認
  - **期待結果**: 3分以内に完了
```

---

## ステップ5: 合否判定

### 判定基準

| 結果 | 条件 |
|------|------|
| **PASS** | 全ての自動検証がパス、かつ手動確認も完了 |
| **CONDITIONAL_PASS** | 自動検証はパス、手動確認が残っている |
| **FAIL** | 1件以上の自動検証が失敗 |

### 判定ロジック

```python
自動検証_PASS = 0
自動検証_FAIL = 0
手動確認_件数 = 0

for 条件 in 受け入れ条件:
    if 条件.カテゴリ in [CODE_EXISTS, CONFIG, BEHAVIOR]:
        if 条件.検証結果 == PASS:
            自動検証_PASS += 1
        else:
            自動検証_FAIL += 1
    else:
        手動確認_件数 += 1

if 自動検証_FAIL > 0:
    総合判定 = "FAIL"
elif 手動確認_件数 > 0:
    総合判定 = "CONDITIONAL_PASS"
else:
    総合判定 = "PASS"
```

---

## ステップ6: レポート出力と保存

### 出力先

レポートは以下のファイルに保存します:

```
Write('[steeringパス]/acceptance-test-report.md', レポート内容)
```

- `.steeringパス指定時`: `[指定パス]/acceptance-test-report.md`
- `--from-idea指定時`: `.steering/[アイデア名]/acceptance-test-report.md`（steeringディレクトリがない場合は作成）
- `引数なし時`: `.steering/[最新ディレクトリ]/acceptance-test-report.md`

### 出力形式

```markdown
# 受け入れテストレポート

> 生成日時: {YYYY-MM-DD HH:MM}
> 対象: {steeringディレクトリ / アイデアファイル}

## サマリー

| 項目 | 件数 |
|------|------|
| 受け入れ条件 総数 | {N} |
| 自動検証 PASS | {N} |
| 自動検証 FAIL | {N} |
| 手動確認 必要 | {N} |
| **総合判定** | **{PASS/CONDITIONAL_PASS/FAIL}** |

## 1. 自動検証結果

### PASS ({N}件)

| # | 条件 | カテゴリ | 根拠 |
|---|------|----------|------|
| 1 | {条件1} | CODE_EXISTS | `minitools/xxx.py:42` |
| 2 | {条件2} | CONFIG | `settings.yaml:15` |

### FAIL ({N}件)

| # | 条件 | カテゴリ | 理由 |
|---|------|----------|------|
| 1 | {条件3} | CODE_EXISTS | クラスが見つからない |

#### FAIL詳細

##### 条件3: {条件内容}
- **期待**: XxxAnalyzerクラスが実装されている
- **実際**: `src/`内に該当クラスなし
- **検索結果**: `Grep('class XxxAnalyzer', 'src/')` → 0件
- **推奨対応**: `src/company_research_agent/services/xxx.py`にXxxAnalyzerクラスを実装

## 2. 手動確認チェックリスト

{ステップ4で生成したチェックリスト}

## 3. 次のアクション

### FAILの場合
- [ ] {FAIL条件1}を修正
- [ ] {FAIL条件2}を修正
- [ ] `/acceptance-test`を再実行

### CONDITIONAL_PASSの場合
- [ ] 手動確認チェックリストを実施
- [ ] 全て確認後、受け入れ条件を完了としてマーク

### PASSの場合
- [ ] 実装完了を宣言
- [ ] アイデアファイルのステータスを更新
```

---

## ステップ7: 結果の反映

### PASSの場合

1. **steeringディレクトリの更新**
   ```
   Edit('[steeringパス]/requirements.md')
   → 全条件を [x] に更新
   ```

2. **アイデアファイルの更新（--from-idea使用時）**
   ```
   Edit('docs/ideas/[ファイル名].md')
   → ステータス: draft → verified
   → 検証日: YYYY-MM-DD
   ```

### CONDITIONAL_PASSの場合

1. **レポートの保存** → ステップ6で実施済み

2. **手動確認の依頼**
   ```
   ユーザーに手動確認チェックリストの実施を依頼
   ```

### FAILの場合

1. **問題箇所の特定**
2. **修正提案の提示**
3. **再検証の案内**

---

## 注意事項

- 自動検証は偽陽性/偽陰性の可能性があるため、結果を確認すること
- 手動確認項目は人間の判断が必要なものを含む
- パフォーマンス条件は環境依存のため、目安として扱う
- テストが存在しない場合、BEHAVIOR条件は手動確認に分類される
