# GitHub Pages 配信元切替手順

対象: リポジトリ管理者（GitHub の Settings を操作できる人）。

**この手順書の番号順を必ず守ってください。順序を崩すと、現在ライブ配信中の
先生のサイト（`index.html` / `style.css`、main ブランチ、GitHub Pages の
「ブランチから配信」モード）を壊すおそれがあります。**

ライブが変わる瞬間は手順3だけです。それ以外の手順ではライブの見た目は
一切変わりません。

---

## 1. setup/hugo-blowfish への push で CI の build ジョブが通ることを確認する

1. `setup/hugo-blowfish` ブランチに push する。
2. GitHub リポジトリの **Actions** タブを開き、該当の run を確認する。
3. `build` ジョブが成功していることを確認する。
4. `deploy` ジョブは **スキップ（Skipped）** 表示になっていることを確認する
   （`setup/hugo-blowfish` への push では `main` ブランチではないため、
   ワークフロー内の条件でデプロイが実行されない設計）。

この時点ではライブの表示は一切変わりません。

---

## 2. main へマージする

1. `setup/hugo-blowfish` から `main` への Pull Request を作成し、マージする。
2. マージしても、リポジトリ直下の `index.html` / `style.css` はそのまま残る
   （このタスクでは削除・移動していない）。
3. **→ この時点でもライブは変わりません。** GitHub Pages がまだ
   「ブランチから配信」モードのままだからです。

### マージ直後の CI 実行について（重要）

main へのマージによって Actions が自動的に走ります。このとき:

- `build` ジョブは成功します。
- `deploy` ジョブは **実行されますが失敗するのが正常です。**
  GitHub Pages の配信元がまだ「Actions」に切り替わっていないため、
  `actions/deploy-pages` がデプロイ先を見つけられずに失敗します。

**この失敗を見て設定を元に戻したり、ワークフローを修正したりする必要は
ありません。** 次の手順3（配信元の切替）を行うための正常な通過点です。

---

## 3. GitHub Pages の配信元を「Actions」へ切り替える

**→ ここが唯一、ライブの配信内容が変わる操作です。** 落ち着いて実施してください。

1. リポジトリの **Settings** タブを開く。
2. 左メニューの **Pages** を開く。
3. **Build and deployment** セクションの **Source** ドロップダウンを確認する。
   - 現在は「Deploy from a branch」になっているはずです。
4. **Source** を **「GitHub Actions」** に変更する。

この操作をした瞬間から、GitHub Pages は Actions がアップロードした
アーティファクト（Hugo のビルド結果 `public/`）を配信するようになります。

---

## 4. workflow_dispatch で再実行する

1. **Actions** タブを開く。
2. 左側のワークフロー一覧から `Hugo CI/CD` を選ぶ。
3. 右側の **Run workflow** ボタンを押す。
4. ブランチに `main` を選んで実行する。
5. `build` → `deploy` の両方が成功することを確認する。

---

## 5. 表示を確認する

以下の URL をブラウザで開き、意図通りに表示されるか確認する。

| URL | 期待する挙動 |
|---|---|
| `https://yamakata.github.io/` | `/ja/` へ即座にリダイレクトされる |
| `https://yamakata.github.io/ja/` | 日本語トップページが表示される |
| `https://yamakata.github.io/en/` | 英語トップページが表示される |
| `https://yamakata.github.io/ja/research/` など各セクション | 対応する日本語ページが表示される |
| `https://yamakata.github.io/en/research/` など各セクション | 対応する英語ページが表示される |
| `https://yamakata.github.io/ja/this-page-does-not-exist/`（存在しないURL） | 独自の404ページ（「ページが見つかりません / Page not found」）が表示される |

各セクションの一覧（日英とも同じパス構成）:
`research` / `contact` / `join` / `access` / `publications` / `news` / `members` / `categories/news`

### noindex が入っていることの確認方法

以下のいずれかの方法で確認する。

- **ブラウザで確認する場合**: 各ページを開き、右クリック →
  「ページのソースを表示」（またはショートカット、ブラウザにより異なる）で
  `<meta name="robots" content="noindex, nofollow">` が `<head>` 内に
  あることを目で確認する。
- **コマンドで確認する場合**（ターミナルが使える場合）:
  ```
  curl -s https://yamakata.github.io/ja/ | grep noindex
  curl -s https://yamakata.github.io/404.html | grep noindex
  ```
  何かしら出力されれば noindex が入っている。

---

## 6. 表示確認後、別コミットで index.html / style.css を _archive/ へ退避する

手順5で表示に問題がないことを確認できたら、**別コミットとして**
リポジトリ直下の `index.html` / `style.css` を `_archive/` ディレクトリへ
移動する（このタスクの範囲外。ユーザー自身が行う）。

同一コミットで手順3〜5と6を混ぜないこと。問題が起きたときに
「どの操作が原因か」を切り分けやすくするため。

---

## 公開時にやること

サイトを実際に検索エンジンに公開する準備ができたら、以下を対応する。

### noindex の解除

`config/_default/params.toml` 内の以下の行を探す:

```toml
# TODO(公開時): 公開前に noindex を解除する
...
robots = "noindex, nofollow"
```

この `robots = "noindex, nofollow"` の行を削除する（または空文字にする）。
これにより `layouts/partials/head.html`（テーマ本体）が出力する
`<meta name="robots">` タグが消え、通常ページのインデックスが許可される。

`layouts/alias.html` にも `<meta name="robots" content="noindex, nofollow">`
が直書きされている（ルートのリダイレクトページと、各セクションの
ページネーション1ページ目のリダイレクトに使われる）。こちらも同時に
外すか、恒久的に残すかは要検討（リダイレクトページ自体は実体のあるコンテンツを
持たないため、外さなくても実害は小さい）。

`static/404.html` の `<meta name="robots" content="noindex, nofollow">` は
404ページなので公開後も残したままでよい（404ページが検索結果に
インデックスされる必要はないため）。

### robots.txt の方針

現状 `enableRobotsTXT = false` を `config/_default/hugo.toml` に明示しており、
robots.txt は生成されない（理由は同ファイルのコメント参照）。
公開後に robots.txt でサイトマップの場所を明示したい場合は、
`enableRobotsTXT = true` に変更するだけでなく、テーマ側の
`[outputs] home` に `ROBOTSTXT` を追加する対応が別途必要になる
（このタスクでは実装していない。公開時に改めて設計・確認すること）。
