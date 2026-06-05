---
name: feature-flow
description: >-
  機能開発の全工程を1コマンドで連結実行するオーケストレーター: brainstorm → plan-feature → implement-feature → acceptance-test → validate-code →〔update-docs → review-docs〕。
  個別の /brainstorm や /plan-feature を手で順に叩く代わりに、アイデア/計画から実装・検証・ドキュメントまで通したい時に使う。
  --auto で plan 承認後を停止せず自動実行（高優先度ゼロまで検証修正ループ）、--from-idea/--from-plan/既存steeringフォルダ指定で途中から開始、--with-docs でドキュメント同期まで、--dry-run で実行計画だけ確認。
  入力（計画/アイデア）が無ければ --auto でも停止して確認するガードレール付き。
user-invocable: true
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
argument-hint: "[機能名|steeringフォルダ] [--from-idea|--from-plan ファイル名] [--auto] [--with-docs] [--max-iterations N] [--dry-run]"
---

# feature-flow（開発フローのオーケストレーション）

**目的:** 既存の単機能スキル（brainstorm / plan-feature / implement-feature / acceptance-test / validate-code / update-docs / review-docs）を、正しい順序・正しい引数・正しい停止ポイントで連結し、機能開発を最後まで通す。

このスキルは**司令塔**であり、各工程の中身を持たない。各工程は対応するサブスキルの `SKILL.md` が唯一の正（source of truth）であり、このスキルはそれを**フェーズ到達時に読み込んで委譲**する。手順を写し取らないこと（写すと必ず劣化・乖離する）。

---

## 引数パターン

| 起動例 | 開始フェーズ | 意味 |
|--------|-------------|------|
| `/feature-flow 機能名` | brainstorm | アイデア整理から最後まで通す |
| `/feature-flow --from-idea [ファイル名]` | plan-feature | brainstormをスキップ、アイデアdocから計画 |
| `/feature-flow --from-plan [ファイル名]` | plan-feature | 計画doc（docs/plan/）から計画 |
| `/feature-flow YYYYMMDD-機能名` | implement-feature | 既存steeringフォルダの計画から実装以降 |

**修飾フラグ（上記と組み合わせ可）:**

| フラグ | 効果 | デフォルト |
|--------|------|-----------|
| `--auto` | plan-feature の承認以降を停止せず自動実行（検証修正ループ含む） | OFF（各フェーズ後に確認） |
| `--with-docs` | 実装・検証の後に update-docs → review-docs を実行 | OFF |
| `--max-iterations N` | 検証/ドキュメント修正ループの上限回数 | 3 |
| `--dry-run` | 実行計画を出力して**何も実行せず停止** | OFF |

引数規約はサブスキルに完全準拠する（`--from-idea` / `--from-plan` / `--from-report`、`YYYYMMDD-` 形式のフォルダ判定）。判定に迷う引数があればユーザーに確認する。

---

## ステップ0: 引数解決とプラン構築

最初に引数を解釈し、**実行プラン**を内部的に確定する。これがこのスキルの頭脳であり、`--dry-run` で外に出す対象でもある。

1. **開始フェーズの決定**
   - 引数が `YYYYMMDD-` 形式で始まる → そのフォルダを steering ディレクトリとみなし、開始 = **implement-feature**
   - `--from-plan` あり → 開始 = **plan-feature**（計画docを取り込む）
   - `--from-idea` あり → 開始 = **plan-feature**（アイデアdocを取り込む。brainstormはスキップ）
   - いずれもなし（機能名のみ or 引数なし）→ 開始 = **brainstorm**

   入力ソース（計画/アイデア/steering）を指定された場合は、**ガードレール G1 に従い実在を確認する**。dry-run では確認は行わず「実行時に実在を検証し、未検出/曖昧なら停止」と計画に明記する。

2. **モードの決定**
   - `--auto` の有無 → 自動モード / インタラクティブモード
   - `--with-docs` の有無 → ドキュメント同期フェーズの有無
   - `--max-iterations`（未指定なら3）

3. **フェーズ列の確定**
   開始フェーズから以下の正準順序で、終端まで並べる:
   ```
   brainstorm → plan-feature → implement-feature → acceptance-test → validate-code
   〔→ update-docs → review-docs〕（--with-docs 時のみ）
   ```

4. **停止ポイントの確定**（後述「停止ポイントの原則」に従う）

`--dry-run` の場合はここで**ステップDR（dry-run出力）へ進み、実行はしない**。
そうでなければステップ1へ進む。

---

## 停止ポイントの原則

なぜ止めるか：brainstorm と plan-feature は「人間が方向を決める」工程だから、自動化すると見当違いの実装に突き進む。逆に implement 以降は計画が固まった後の機械的な工程なので、`--auto` なら任せられる。

| フェーズ | 停止するか |
|---------|-----------|
| brainstorm | **常に対話**（ユーザーが「保存して」と言うまで継続。性質上スキップ不可の人間工程） |
| plan-feature | **常にユーザー確認で停止**（計画の承認ゲート。ここが全体の要） |
| implement-feature 以降 | `--auto` あり → **停止しない**／`--auto` なし → **各フェーズ後に成果物を提示して確認** |

plan-feature の承認は飛ばさない。`--auto` でも、計画承認のゲートだけは人間が通す（開始フェーズが implement 以降＝既に計画がある場合を除く）。

---

## ガードレール（暴走防止）

司令塔として最も避けたいのは「土台が無いのに突き進んで、見当違いの実装を量産する」こと。`--auto` は便利だが、誤った前提の上で自動化すると被害が増幅する。次の3つは `--auto` の有無に関わらず常に守る。

### G1. 入力ソースの実在を確認してから進む（推測で新規作成に倒さない）

`--from-plan [名前]` / `--from-idea [名前]` / steering フォルダ指定で対象を受け取ったら、**フェーズ実行に入る前にその実在を確認する**:
```
--from-plan 名前   → Glob('docs/plan/*名前*.md')
--from-idea 名前   → Glob('docs/ideas/*名前*.md')
steering フォルダ  → Glob('.steering/[フォルダ名]/*')
```
- **0件（見つからない）**: 推測で「新規機能」とみなして進めてはいけない。`--auto` でも**停止し**、「該当が見つからない。新規作成するか／別名を指定するか」をユーザーに確認する。
- **複数候補で曖昧**: どれを使うか**停止して確認**する。
- **1件**: そのファイル/フォルダを確定して進む。

なぜ `--auto` でも止めるか：計画やアイデアという「土台」が無いまま進むと、別物を作ってしまう。土台の欠落は `--auto` が前提とする「計画は固まっている」を満たさないので、自動化の対象外と考える。

### G2. 解決済みプランに無いフェーズを足さない（スコープ厳守）

ステップ0で確定したフェーズ列だけを実行する。特に **update-docs / review-docs は `--with-docs` 指定時のみ**。指定が無いのに「ついでにドキュメントも」と足さない。指示していない作業を勝手に増やすのは、たとえ善意でも信頼を損なう。中/低優先度の指摘や追加提案は「実行」せず、最後の要約報告で**提案として**伝えるに留める。

### G3. 「最新アイデア」の陳腐化を一言確認する

`--from-idea`（特にファイル名未指定で最新を自動選択）の場合、選んだアイデアが**既に実装済み**のことがある（アイデアファイルの status が `draft` のまま、実装・コミットだけ先に済んでいるケースは珍しくない）。plan-feature に渡す前に軽く確認する:
- アイデアファイルの status / 完了条件チェックボックス
- 同名・関連の実装が既に存在しないか（`git log` のコミットメッセージや該当コードの有無）

既に実装済みらしき場合は、その旨を提示して「差分・取りこぼしの補完として進めるか／別アイデアにするか」を確認する。既存機能の再実装を防ぐための軽量チェックであり、深掘り調査はしない（重複検出の本責務は brainstorm / plan-feature 側にある）。

---

## ステップ1〜: フェーズ実行（共通手順）

各フェーズは次の手順で実行する:

1. **サブスキルの手順を読む(just-in-time)**
   フェーズ到達時に、対応する `SKILL.md` をその場で読み込む。最初に全部読まない（長時間の実行でコンテキストを浪費しないため）。
   - brainstorm: `.claude/skills/brainstorm/SKILL.md`
   - plan-feature: `.claude/skills/plan-feature/SKILL.md`
   - implement-feature: `.claude/skills/implement-feature/SKILL.md`
   - acceptance-test: `.claude/skills/acceptance-test/SKILL.md`
   - validate-code: `.claude/skills/validate-code/SKILL.md`
   - update-docs: `.claude/skills/update-docs/SKILL.md`
   - review-docs: `.claude/skills/review-docs/SKILL.md`

2. **適切な引数で手順を実行する**
   そのサブスキルを単独起動したのと同じ引数を渡す。フェーズ間の受け渡しは既存の共有状態（`.steering/[日付]-[機能名]/` ディレクトリと `docs/`）を介す。サブスキルが steering フォルダを生成・特定したら、その**フォルダ名を以降の全フェーズで使い回す**（毎回最新を再検出させない＝取り違え防止）。

3. **完了したら停止ポイントの原則に従う**
   - 対話/確認が必要なフェーズ → 成果物を要約提示して待つ
   - `--auto` で自動継続 → 次フェーズへ

### フェーズ間の受け渡し早見表

| 前フェーズ | 生成物 | 次フェーズへの渡し方 |
|-----------|--------|---------------------|
| brainstorm | `docs/ideas/*.md` | plan-feature を `--from-idea [そのファイル]` で起動 |
| plan-feature | `.steering/[日付]-[機能名]/{requirements,design,tasklist}.md` | implement-feature に**そのフォルダ名**を渡す |
| implement-feature | 実装コード + tasklist 進捗 | acceptance-test / validate-code に同フォルダ名 |
| acceptance-test | `[steering]/acceptance-test-report.md` | 不合格時 implement-feature `--from-report` |
| validate-code | `[steering]/validation-report.md` | 不合格時 implement-feature `--from-report` |
| update-docs | docs/CLAUDE/README 更新 | review-docs に同フォルダ名 |
| review-docs | `[steering]/review-report.md` | 不合格時 update-docs `--from-report` |

---

## 検証修正ループ（acceptance-test / validate-code）

implement-feature の後、acceptance-test と validate-code を実行する。両者は steering フォルダにレポートを出す。

**合格（クリーン）の基準:** 両レポートとも**優先度「高」の指摘がゼロ**であること。
- acceptance-test: 高優先度の不合格条件がない（中/低の手動確認事項は残ってよい）
- validate-code: 優先度「高」の UNRESOLVED がない（中/低のみなら CONDITIONAL_PASS 扱いで合格とする）

中・低優先度の指摘はレポートに残し、ループ終了後にユーザーへ申し送る。

### ループ手順

```
iteration = 0
前回の高優先度件数 = ∞
while True:
    acceptance-test を実行 → acceptance-test-report.md
    validate-code を実行   → validation-report.md
    高優先度件数 = 両レポートの優先度「高」指摘の合計

    if 高優先度件数 == 0:
        → 合格。ループを抜ける
    if iteration >= max-iterations:
        → 上限到達。レポートを提示して停止し、ユーザーに判断を委ねる
    if 高優先度件数 >= 前回の高優先度件数:
        → 停滞（減っていない/増えた）。これ以上の自動修正は無益。
          レポートを提示して停止し、ユーザーに判断を委ねる

    # 自動修正
    implement-feature --from-report [steering フォルダ] --high を実行
    前回の高優先度件数 = 高優先度件数
    iteration += 1
```

- `--auto` 時: 上記ループを自動で回す。
- `--auto` なし時: ループは回さず、各レポートを提示して「修正するか / 自分で直すか / このまま進むか」をユーザーに確認する。

「停滞検知」を入れる理由：validate の指摘を直すと acceptance が再び崩れる、といった振動で上限まで無駄に回り続けるのを防ぐため。減っていなければ人間に返すのが正しい。

---

## ドキュメント同期ループ（--with-docs 時のみ）

検証修正ループが合格で抜けた後にのみ実行する（未完成のコードをドキュメント化しないため）。

1. update-docs を steering フォルダ指定で実行（実装内容に絞って docs/CLAUDE/README を同期）
2. review-docs を同フォルダ指定で実行 → `review-report.md`
3. review-report に**優先度「高」の指摘**があれば、update-docs `--from-report` で修正 → 再 review-docs
4. 終了条件は検証ループと同じ（高優先度ゼロ / 上限到達 / 停滞）

---

## ステップDR: dry-run 出力

`--dry-run` 指定時は、ステップ0で確定したプランを**以下の固定フォーマットで出力して終了**する。実行は一切しない。これは破壊的なマルチフェーズ実行前の安全確認であり、ルーティングの自己点検でもある。

ALWAYS この構造で出力する:

```
# feature-flow 実行計画（dry-run）

## 解析結果
- 開始フェーズ: <brainstorm | plan-feature | implement-feature>
- モード: <インタラクティブ | 自動(--auto)>
- ドキュメント同期: <あり(--with-docs) | なし>
- 修正ループ上限: <N> 回
- 入力ソース: <機能名 / アイデアファイル / 計画ファイル / steeringフォルダ>
- 入力ソース検証: <実行時に実在を確認。未検出/曖昧なら --auto でも停止して確認（G1）／機能名のみのため検証不要>

## 実行フェーズ
1. <フェーズ名> — <停止: 人間確認 | 自動 | 対話>
2. ...
（実行されないフェーズは「スキップ」と明記）

## 停止ポイント（人間が介在する箇所）
- <フェーズ名>: <理由>
- ...

## 検証修正ループ
- 対象: acceptance-test, validate-code
- 合格基準: 優先度「高」の指摘ゼロ
- 終了条件: 合格 / 上限 <N> 回 / 停滞（高優先度件数が減らない）
- 自動修正: <有効(--auto) | 無効（各レポートで確認）>
```

ドキュメント同期が ON の場合は「ドキュメント同期ループ」セクションも同様に追記する。

---

## 全体の進め方の要約

1. 引数を解析してプランを確定（ステップ0）
2. `--dry-run` ならプランを出力して終了
3. 開始フェーズから順に、各サブスキルの SKILL.md を都度読んで委譲実行
4. brainstorm（対話）と plan-feature（承認）は必ず人間を通す
5. implement 以降は `--auto` なら検証修正ループまで自動、なければ各フェーズで確認
6. `--with-docs` ならドキュメント同期ループまで実行
7. 最後に、通過した全フェーズ・残った中/低優先度の指摘・ループ回数を要約報告する

途中でサブスキルがエラー（前提ファイル欠落など）を返したら、そのサブスキルのエラーメッセージをそのまま提示し、勝手に先へ進まない。
