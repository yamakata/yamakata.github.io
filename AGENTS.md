cat > AGENTS.md <<'EOF'
# AGENTS.md

## このリポジトリについて
東京大学 情報基盤センター 山肩研究室の公式ウェブサイト。
Hugo + Blowfish v3 テーマ による静的サイト。
GitHub Pages のユーザーサイトとして https://yamakata.github.io/ で公開されている。

## 現在の状況（重要）
- main ブランチのルートにある index.html / style.css が **現在ライブで配信中**。
  移行が完了するまで、これらを削除・破壊しない。
- Hugo への移行作業は setup/ 系のブランチで行い、main へは PR 経由でのみ入れる。

## 絶対に守ること
- テーマ本体（Hugo Modules のキャッシュ、`themes/` 配下）を直接編集しない。
  カスタマイズは必ずプロジェクト側の `layouts/` `assets/` `i18n/` でオーバーライドする。
- go.mod / go.sum / config/_default/module.toml を勝手に書き換えない。
- CMS・サーバサイド実行環境は導入しない。生成物は完全な静的ファイルであること。
- URL 構造を変更する場合は必ず事前に確認を取る。既存 URL は壊さない。
- 業績データは `data/` 配下の生成物であり、手書きしない。
  元データは `content-source/publications.bib`。
- 日本語コンテンツは `content/ja/`、英語は `content/en/` に置く。
  片方だけ追加して終わりにせず、対応する言語のプレースホルダも作る。
- 研究室メンバー・業績・研究内容について、確認の取れていない情報を추測で書かない。
  不明点は TODO コメントとして残し、報告する。

## 構成
- Hugo: 0.162.0 以上（ローカルは 0.165.0）
- テーマ: github.com/nunocoracao/blowfish/v3（Hugo Modules 経由）
- 設定: config/_default/ 配下に分割
- 言語: ja がデフォルト（ルート配信）、en は /en/ 配下

## コマンド
- 開発サーバ: `hugo server -D`
- 本番ビルド: `hugo --minify`
- テーマ更新: `hugo mod get -u`
- 業績データ生成: `python scripts/bib2yaml.py`

## コーディング方針
- Hugo のテンプレートは partial に分割し、1ファイル100行を超えない。
- 画像は `assets/` に置き、Hugo の image processing 経由で出力する。`static/` に直接置かない。
- ハードコードした文言はテンプレートに書かず `i18n/*.yaml` に置く。

## 変更時の完了条件
- `hugo --minify` がエラー・警告なしで通る
- 日本語版・英語版の両方でビルドされる
- 変更点の要約を日本語で報告する
EOF