# circleci-pr-trigger
Triggers a CircleCI build on PR + more

This is a small flask app to do 2 tasks:
1. Start a CircleCi build when a pull request is opened
2. Rebuild when new commits are added
3. Cancel ongoing builds for a branch when starting a new build

It isn't ready for general consumption yet, but will be soon.

## circle.yml config
To use this, you want to configure CircleCI to only build master by default -- we will trigger builds of non-master branches.
Include the following in your circle.yml:
```
general:
   branches:
     only:
       - master
```
