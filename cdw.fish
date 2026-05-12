# ~/.config/fish/functions/cdw.fish
#
# `cdw`       → cd into current workspace's worktree
# `cdw foo`   → cd into the `foo` workspace
function cdw --description "cd into a wk workspace"
    set -l target (wk cd $argv)
    or return 1
    cd $target
end
