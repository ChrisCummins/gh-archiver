# Copyright 2017-2020 Chris Cummins <chrisc.101@gmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
"""Mirror a Github user's repos locally.

This program fetches a Github user's repositories and mirrors them to a local
directory. New repositories are cloned, existing repositories are fetched from
remote.

Setup:

    Create a Github personal access token by visiting
    <https://github.com/settings/tokens/new>. If you intend to mirror your own
    private repositories, select "repo" from the list of available scopes. To
    mirror only your public repositories or those another user, no scopes are
    required..

    Create a ~/.github/access_tokens/gh_archiver.txt file containing your
    the personal access token you just created:

        $ mkdir -p ~/.github/access_tokens
        $ cat <<EOF > ~/.github/access_tokens/gh_archiver.txt
        YourAccessToken
        EOF
        $ chmod 0600 ~/.github/access_tokens/gh_archiver.txt

Usage:

    Mirror a Github user's repositories to a directory using:

        $ gh_archiver --user <github_username> --outdir <path>
"""
import os
import pathlib
import shutil
import sys
from typing import Iterator
from typing import Union

from git import Repo
from github import AuthenticatedUser
from github import NamedUser
from github.Repository import Repository as GithubRepository

from datasets.github import api
from labm8.py import app
from tools.git import git_clone

FLAGS = app.FLAGS

app.DEFINE_string("user", None, "Github username")
app.DEFINE_output_path(
  "outdir",
  pathlib.Path("~/gh_archiver").expanduser(),
  "The directory to clone repositories to.",
)
app.DEFINE_boolean(
  "delete",
  False,
  "Delete all other files in the output directory. Disabling this feature will "
  "cause deleted repositories to accumulate.",
)
app.DEFINE_list(
  "repo",
  [],
  "White list repositories to include. If set, only these repositories will be "
  "cloned.",
)
app.DEFINE_list("exclude", [], "A list of repositories to exclude.")
app.DEFINE_boolean(
  "force_https",
  False,
  "If set, force using HTTPS git remotes, even when SSH is available.",
)


def get_repos(user) -> Iterator[GithubRepository]:
  """ get user repositories """
  excluded = set(FLAGS.exclude)
  included = set(FLAGS.repo)
  for repo in user.get_repos():
    if included and repo.name not in included:
      continue
    if repo.name not in excluded:
      yield repo


def truncate(string: str, maxlen: int, suffix=" ...") -> str:
  """ truncate a string to a maximum length """
  if len(string) > maxlen:
    return string[: maxlen - len(suffix)] + suffix
  else:
    return string


def main():
  if not FLAGS.user:
    raise app.UsageError("--user not set")

  try:
    g = api.GetDefaultGithubConnectionOrDie(
      extra_access_token_paths=["~/.github/access_tokens/gh_archiver.txt"]
    )

    # AuthenticatedUser provides access to private repos
    user: Union[NamedUser, AuthenticatedUser] = g.get_user(FLAGS.user)

    repos = list(get_repos(user))

    FLAGS.outdir.mkdir(exist_ok=True, parents=True)

    if FLAGS.delete:
      # Delete any directories which are not Github repos.
      repo_names = [r.name for r in repos]

      for path in FLAGS.outdir.iterdir():
        if not path.is_dir():
          continue
        local_repo_name = os.path.basename(path)

        if local_repo_name not in repo_names:
          print(f"removing {local_repo_name}")
          if path.is_dir():
            shutil.rmtree(path)
          else:
            os.remove(path)

    errors = False
    for repo in repos:
      local_path = FLAGS.outdir / repo.name

      # remove any file of the same name
      if local_path.exists() and not local_path.is_dir():
        os.remove(local_path)

      # Local clone
      if local_path.is_dir():
        print(f"updating {repo.name}")
      else:
        print(f"cloning {repo.name}:{repo.default_branch}")
        try:
          api.CloneRepo(repo, local_path)
        except git_clone.RepoCloneFailed as e:
          errors = True
          print(f"ERROR: {local_path} {type(e).__name__}", file=sys.stderr)

      try:
        local_repo = Repo(local_path)
        for remote in local_repo.remotes:
          remote.fetch()
        for submodule in local_repo.submodules:
          submodule.update(init=True)
      except Exception as e:
        errors = True
        print(f"ERROR: {local_path} {type(e).__name__}", file=sys.stderr)

    return sys.exit(1 if errors else 0)
  except KeyboardInterrupt:
    print()
    sys.exit(1)


if __name__ == "__main__":
  app.Run(main)
