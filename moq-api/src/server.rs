use std::net;

use axum::{
	extract::{Path, State},
	http::StatusCode,
	response::{IntoResponse, Response},
	routing::{get,delete},
	Json, Router,
};

use clap::Parser;

use redis::{aio::ConnectionManager, AsyncCommands};

use moq_api::{ApiError, Origin};
use url::Url;

/// Runs a HTTP API to create/get origins for broadcasts.
#[derive(Parser, Debug)]
#[command(author, version, about, long_about = None)]
pub struct ServerConfig {
	/// Listen for HTTP requests on the given address
	#[arg(long)]
	pub listen: net::SocketAddr,

	/// Connect to the given redis instance
	#[arg(long)]
	pub redis: url::Url,
}

pub struct Server {
	config: ServerConfig,
}

impl Server {
	pub fn new(config: ServerConfig) -> Self {
		Self { config }
	}

	pub async fn run(self) -> Result<(), ApiError> {
		log::info!("connecting to redis: url={}", self.config.redis);

		// Create the redis client.
		let redis = redis::Client::open(self.config.redis)?;
		let redis = redis
			.get_tokio_connection_manager() // TODO get_tokio_connection_manager_with_backoff?
			.await?;

		let app = Router::new()
				.route(
					"/origin/:relayid/:id",
					get(get_origin)
						.post(set_origin)
				)
				.route(
					"/origin/:id",
						delete(delete_origin)
						.patch(patch_origin),
				)
			.with_state(redis);

		log::info!("serving requests: bind={}", self.config.listen);

		axum::Server::bind(&self.config.listen)
			.serve(app.into_make_service())
			.await?;

		Ok(())
	}
}

async fn get_origin(
	Path((relayid, id)): Path<(String, String)>,
		State(mut redis): State<ConnectionManager>,
) -> Result<Json<Origin>, AppError> {
	let key = origin_key(&id, &relayid);
	let payload: Option<String> = redis.get(&key).await?;
	let payload = payload.ok_or(AppError::NotFound)?;
	let origin: Origin = serde_json::from_str(&payload)?;
	Ok(Json(origin))
}

async fn set_origin(
	State(mut redis): State<ConnectionManager>,
    Path((relayid, id)): Path<(String, String)>,
		Json(origin): Json<Origin>,
) -> Result<(), AppError> {
	// TODO validate origin
	if relayid != "4443" {
		return Err(AppError::Parameter(url::ParseError::IdnaError));
	}

	// here would i have the logic
	// right know we need that if 4442 sets an origin then it should create
	//   one for 4443 that points to 4442 that is the default so the imp step is the add 4443 to the path
	let key = origin_key(&id, "4444");

	// Convert the input back to JSON after validating it add adding any fields (TODO)
	let payload = serde_json::to_string(&origin)?;

	//   one for 1 that points to 2
	let key2 = origin_key(&id, "4445");

	let mut url = Url::parse(&origin.url.to_string()).unwrap();
	url.set_port(Some(4444)).unwrap();
	let origin2 = Origin {
		url: Url::parse(&url.to_string()).unwrap(),
	};
	let payload2 = serde_json::to_string(&origin2)?;

	//   one for 1 that points to 2
	let key3 = origin_key(&id, "4443");

	let payload3 = serde_json::to_string(&origin)?;



	// Attempt to get the current value for the key
	let current: Option<String> = redis::cmd("GET").arg(&key).query_async(&mut redis).await?;

	if let Some(current) = &current {
		if current.eq(&payload) {
			// The value is the same, so we're done.
			return Ok(());
		} else {
			return Err(AppError::Duplicate);
		}
	}

	let res: Option<String> = redis::cmd("SET")
	.arg(key)
	.arg(payload)
	.arg("NX")
	.arg("EX")
	.arg(600) // Set the key to expire in 10 minutes; the origin needs to keep refreshing it.
	.query_async(&mut redis)
	.await?;


	let res2: Option<String> = redis::cmd("SET")
	.arg(key2)
	.arg(payload2)
	.arg("NX")
	.arg("EX")
	.arg(600) // Set the key to expire in 10 minutes; the origin needs to keep refreshing it.
	.query_async(&mut redis)
	.await?;

	let res3: Option<String> = redis::cmd("SET")
	.arg(key3)
	.arg(payload3)
	.arg("NX")
	.arg("EX")
	.arg(600) // Set the key to expire in 10 minutes; the origin needs to keep refreshing it.
	.query_async(&mut redis)
	.await?;

	if res.is_none() || res2.is_none()|| res3.is_none() {
		return Err(AppError::Duplicate);
	}

	Ok(())
}

async fn delete_origin(Path(id): Path<String>, State(mut redis): State<ConnectionManager>) -> Result<(), AppError> {
	let key = format!("*{}", id);
	match redis.del(key).await? {
		0 => Err(AppError::NotFound),
		_ => Ok(()),
	}
}

// Update the expiration deadline.
async fn patch_origin(
	Path(id): Path<String>,
	State(mut redis): State<ConnectionManager>,
	Json(origin): Json<Origin>,
) -> Result<(), AppError> {
    let pattern = format!("*{}", id);
    let keys: Vec<String> = redis::cmd("KEYS").arg(&pattern).query_async(&mut redis).await?;
	// Make sure the contents haven't changed
	// TODO make a LUA script to do this all in one operation.
	for key in keys {
		let payload: Option<String> = redis.get(&key).await?;
		let payload = payload.ok_or(AppError::NotFound)?;
		let expected: Origin = serde_json::from_str(&payload)?;

		if expected != origin {
			return Err(AppError::Duplicate);
		}
	}

	Ok(())

}


fn origin_key(id: &str,relayid: &str) -> String {
	log::info!("!!!me made this : origin.{}.{}",relayid, id);
	format!("origin.{}.{}",relayid, id)
}

#[derive(thiserror::Error, Debug)]
enum AppError {
	#[error("redis error")]
	Redis(#[from] redis::RedisError),

	#[error("json error")]
	Json(#[from] serde_json::Error),

	#[error("not found")]
	NotFound,

	#[error("duplicate ID")]
	Duplicate,

	#[error("url error in parameter: {0}")]
	Parameter(#[from] url::ParseError),
}

// Tell axum how to convert `AppError` into a response.
impl IntoResponse for AppError {
	fn into_response(self) -> Response {
		match self {
			AppError::Redis(e) => (StatusCode::INTERNAL_SERVER_ERROR, format!("redis error: {}", e)).into_response(),
			AppError::Json(e) => (StatusCode::INTERNAL_SERVER_ERROR, format!("json error: {}", e)).into_response(),
			AppError::NotFound => StatusCode::NOT_FOUND.into_response(),
			AppError::Duplicate => StatusCode::CONFLICT.into_response(),
			AppError::Parameter(e) => (StatusCode::BAD_REQUEST, format!("parameter error: {}", e)).into_response(),
		}
	}
}
