import requests


class CircleCi(object):
	def __init__(self, token, username, project):
		self.token = token
		self.username = username
		self.project = project

	"""
	curl -X POST --header "Content-Type: application/json" -d '{
	  "parallel": 2, //optional, default null
	  "revision": "f1baeb913288519dd9a942499cef2873f5b1c2bf" // optional
	  "build_parameters": { // optional
	    "RUN_EXTRA_TESTS": "true"
	  }
	}
	' https://circleci.com/api/v1/project/:username/:project/tree/:branch?circle-token=:token
	"""
	def start_build(self, branch, rev):
		return requests.post(
			'https://circleci.com/api/v1/project/%s/%s/tree/%s?circle-token=%s' % (self.username, self.project, branch, self.token),
			json = {
				"revision": rev
			}
		)

	"""curl -X POST https://circleci.com/api/v1/project/:username/:project/:build_num/cancel?circle-token=:token"""
	def cancel_build(self, build_num):
		return requests.post('https://circleci.com/api/v1/project/%s/%s/%s/cancel?circle-token=%s' % (self.username, self.project, build_num, self.token))