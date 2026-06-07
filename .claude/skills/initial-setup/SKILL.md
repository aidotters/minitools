---
name: initial-setup
description: プロジェクト初期セットアップ（新規/既存対応）
user-invocable: true
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# 初期セットアップ (initial-setup)

**目的:** Claude Commands/Skillsをプロジェクトに適合させる

**対応モード:**
- **既存プロジェクト**: Commands/Skillsの適合
- **新規プロジェクト**: 基本構成作成 + 適合

**使用方法（別プロジェクトでの導入）:**
```bash
# 1. テンプレートの .claude/ をコピー
cp -r /path/to/_common/.claude /path/to/new-project/

# 2. 新プロジェクトで /initial-setup を実行
# → プロジェクトに合わせて自動適合
```

---
## セットアップの流れ（6ステップ）

**各ステップの詳細手順・置換パターン・言語別 CLAUDE.md テンプレートは [reference.md](./reference.md) を参照してください。実行前に必ず reference.md を読むこと。**

| ステップ | 内容 |
|----------|------|
| 1 | プロジェクト状態の検出（言語・ソース/テストDir・設定ファイル） |
| 2 | セットアップモードの判定（下記ロジック・AskUserQuestion で確認） |
| 3 | 基本構成の作成（初期化モードのみ：ディレクトリ/CLAUDE.md/.env.example/.gitignore） |
| 4 | Commands/Skills の適合（パス・コマンドのパターン置換） |
| 5 | docs/core/ の準備（/gen-all-docs の案内） |
| 6 | 完了レポートとユーザー確認（**このステップで停止**） |

### セットアップモード判定ロジック

| CLAUDE.md | ソースDir | モード | 処理内容 |
|-----------|-----------|--------|----------|
| あり | あり | 適合モード | Commands/Skillsの適合のみ |
| なし | あり | 適合モード + CLAUDE.md生成 | CLAUDE.md生成 → 適合 |
| なし | なし | 初期化モード | 全て新規作成 |

## 完了条件

このワークフローは、以下の条件を満たした時点で完了（ユーザー確認待ち）となる:

- プロジェクト状態が検出されている
- セットアップモードが決定されている
- (初期化モードの場合) 基本構成が作成されている
- Commands/Skills が適合されている
- 完了レポートがユーザーに提示されている

---

> 上記の各ステップの具体的なコマンド例・置換表・出力フォーマット・完了レポート雛形・言語別テンプレートは、すべて [reference.md](./reference.md) に収録しています。
