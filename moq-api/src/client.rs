use url::Url;

use crate::{ApiError, Origin};

#[derive(Clone)]
pub struct Client {
	// The address of the moq-api server
	url: Url,

	client: reqwest::Client,

	relayid: String,

	original: bool,
}

impl Client {
	pub fn new(url: Url, node:Url, original: bool) -> Self {
		let client = reqwest::Client::new();
		let parts:Vec<&str> = node.host_str().unwrap().split('.').collect();
		log::debug!("{:?}",parts);

		if parts.len() > 3 {
			Self { url: url.clone(), client, relayid:parts[3].to_string() , original }
		} else {
			log::info!("The hostname is not an IPv4 address. The specified API won't work.");
			Self { url: url.clone(), client, relayid:"".to_string() , original:false }
		}
	}

	pub async fn get_origin(&self, namespace: &str) -> Result<Option<Origin>, ApiError> {
		let url;
		if self.original {
			url = self.url.join("origin/")?.join(namespace)?;
		}
		else {
			url = self.url.join(&format!("origin/{}/{}", self.relayid.to_string(), namespace))?;
		}

		let resp = self.client.get(url).send().await?;
		if resp.status() == reqwest::StatusCode::NOT_FOUND {
			return Ok(None);
		}
		let origin: Origin = resp.json().await?;
		Ok(Some(origin))
	}

	pub async fn set_origin(&self, namespace: &str, origin: Origin) -> Result<(), ApiError> {
		let url: Url;
		if self.original {
			 url = self.url.join("origin/")?.join(namespace)?;
		}
		else {
			let rest=self.relayid.clone().to_string()+"/"+namespace;
			 url = self.url.join("origin/")?.join(&rest)?;
		}


		let resp = self.client.post(url).json(&origin).send().await?;
		resp.error_for_status()?;

		Ok(())
	}

	pub async fn delete_origin(&self, namespace: &str) -> Result<(), ApiError> {
		let url = self.url.join("origin/")?.join(namespace)?;

		let resp = self.client.delete(url).send().await?;
		resp.error_for_status()?;

		Ok(())
	}

	pub async fn patch_origin(&self, namespace: &str, origin: Origin) -> Result<(), ApiError> {
		let url = self.url.join("origin/")?.join(namespace)?;

		let resp = self.client.patch(url).json(&origin).send().await?;
		resp.error_for_status()?;

		Ok(())
	}
}
