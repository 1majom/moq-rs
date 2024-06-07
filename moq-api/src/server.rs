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
        log::warn!("!!!not the expected publisher relay {}", relayid);
        return Err(AppError::Parameter(url::ParseError::IdnaError));
    }
	//adding routes
	//4443 -> 4441 -> 4444
	//4444 -> 4441 -> 4443

	let preinfo =[
		(4443,4441),
		// (4441,4444)
	];

	//for docker reasons right now we have to provide the hostname also
	let mut relay_info: Vec<(String, String, u16)> = Vec::new();
	for &(src, dest) in &preinfo {
		relay_info.push((src.to_string(), format!("relay{}", dest), dest));
		relay_info.push((dest.to_string(), format!("relay{}", src), src));
	}

	for (src_key_id, dst_host, dst_port) in relay_info.into_iter() {
        let key = origin_key(&id, &src_key_id);
        let mut url = Url::parse(&origin.url.to_string()).unwrap();
        let _ = url.set_port(Some(dst_port));
        let _ = url.set_host(Some(dst_host.as_str()));
        let new_origin = Origin {
            url: Url::parse(&url.to_string()).unwrap(),
        };
        let payload = serde_json::to_string(&new_origin)?;

        // Attempt to get the current value for the key
        let current: Option<String> = redis::cmd("GET").arg(&key).query_async(&mut redis).await?;

        if let Some(current) = &current {
            if current.eq(&payload) {
                // The value is the same, so we're done.
                continue;
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

        if res.is_none() {
            return Err(AppError::Duplicate);
        }
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
