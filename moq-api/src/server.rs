use std::{collections::{HashSet, VecDeque}, net};

use axum::{
	extract::{Path, State},
	http::StatusCode,
	response::{IntoResponse, Response},
	routing::{get,delete},
	Json, Router,
};

use clap::Parser;

use redis::{aio::ConnectionManager, AsyncCommands};

use moq_api::Origin;
use url::Url;
use serde::{Serialize,Deserialize};


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

    /// Topology file contents
    #[arg(long)]
    pub topo_path: std::path::PathBuf,
}

impl ServerConfig {
	pub fn topo(&self) -> Result<String, std::io::Error> {
		std::fs::read_to_string(&self.topo_path)
	}
}

pub struct Server {
	config: ServerConfig,
    topo: String,
}
#[derive(Clone)]
pub struct AppState {
    redis: ConnectionManager,
    topo: String
}


impl Server {
	pub fn new(config: ServerConfig) -> Self {
		let topo = match config.topo() {
			Ok(s) => s,
			Err(e) => {
				eprintln!("Error reading topo: {}", e);
				return Self { config, topo: String::new() };
			}
		};

		Self { config, topo }
	}

	pub async fn run(self) -> Result<(), Box<dyn std::error::Error>> {
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
				.with_state(AppState { redis, topo: self.topo });


		log::info!("serving requests: bind={}", self.config.listen);

		axum::Server::bind(&self.config.listen)
			.serve(app.into_make_service())
			.await?;

		Ok(())
	}
}

async fn get_origin(
	Path((relayid, id)): Path<(String, String)>,
	State(mut state): State<AppState>,
) -> Result<Json<Origin>, AppError> {


	let key = origin_key(&id, &relayid);
	let payload: Option<String> = state.redis.get(&key).await?;
	let payload = payload.ok_or(AppError::NotFound)?;
	let origin: Origin = serde_json::from_str(&payload)?;
	Ok(Json(origin))
}

#[derive(Debug, Deserialize, Serialize)]
struct Topology {
    nodes: Vec<String>,
    edges: Vec<(String, String)>,
}

async fn set_origin(
    State(mut state): State<AppState>,
	Path((relayid, id)): Path<(String, String)>,
    Json(origin): Json<Origin>,
) -> Result<(), AppError> {

	let topo: Topology = serde_yaml::from_str(&state.topo).map_err(|_| AppError::Parameter(url::ParseError::IdnaError))?;
	if !topo.nodes.contains(&relayid) {
		log::warn!("!!!not the expected publisher relay {}", relayid);
		return Err(AppError::Parameter(url::ParseError::IdnaError));
	}

	let mut preinfo: Vec<(u16, u16)> = Vec::new();
    let mut queue: VecDeque<String> = VecDeque::new();
    let mut visited: HashSet<String> = HashSet::new();

    queue.push_back(relayid.clone());
    visited.insert(relayid.clone());


	// Getting the edges that will be used for that exact relayid
    while let Some(node) = queue.pop_front() {
        for (from, to) in &topo.edges {
            if from == &node && !visited.contains(to) {
                let from_u32 = from.parse().unwrap();
                let to_u32 = to.parse().unwrap();
                preinfo.push((to_u32, from_u32));
                queue.push_back(to.clone());
                visited.insert(to.clone());
            } else if to == &node && !visited.contains(from) {
                let from_u32 = from.parse().unwrap();
                let to_u32 = to.parse().unwrap();
                preinfo.push((from_u32, to_u32));
                queue.push_back(from.clone());
                visited.insert(from.clone());
            }
        }
    }


	//for docker reasons right now we have to provide the hostname also
	let mut relay_info: Vec<(String, String, u16)> = Vec::new();
	for &(src, dest) in &preinfo {
		relay_info.push((src.to_string(), format!("relay{}", dest), dest));
	}



	for (src_key_id, dst_host, dst_port) in relay_info.into_iter() {
        let key = origin_key(&id, &src_key_id);
        let mut url = Url::parse(&origin.url.to_string()).unwrap();
		println!("url: {:?}", url);
        let _ = url.set_port(Some(dst_port));
        let _ = url.set_host(Some(dst_host.as_str()));

		println!("url: {:?}", url);

        let new_origin = Origin {
            url: Url::parse(&url.to_string()).unwrap(),
        };
        let payload = serde_json::to_string(&new_origin)?;

        // Attempt to get the current value for the key
        let current: Option<String> = redis::cmd("GET").arg(&key).query_async(&mut state.redis).await?;

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
            .query_async(&mut state.redis)
            .await?;

        if res.is_none() {
            return Err(AppError::Duplicate);
        }
    }

    Ok(())
}

async fn delete_origin(Path(id): Path<String>, State(mut state): State<AppState>,) -> Result<(), AppError> {
	let key = format!("*{}", id);
	match state.redis.del(key).await? {
		0 => Err(AppError::NotFound),
		_ => Ok(()),
	}
}

// Update the expiration deadline.
async fn patch_origin(
	Path(id): Path<String>,
	State(mut state): State<AppState>,
	Json(origin): Json<Origin>,
) -> Result<(), AppError> {
    let pattern = format!("*{}", id);
    let keys: Vec<String> = redis::cmd("KEYS").arg(&pattern).query_async(&mut state.redis).await?;
	// Make sure the contents haven't changed
	// TODO make a LUA script to do this all in one operation.
	for key in keys {
		let payload: Option<String> = state.redis.get(&key).await?;
		let payload = payload.ok_or(AppError::NotFound)?;
		let expected: Origin = serde_json::from_str(&payload)?;

		if expected != origin {
			return Err(AppError::Duplicate);
		}
	}

	Ok(())

}


fn origin_key(id: &str,relayid: &str) -> String {
	format!("origin.{}.{}",relayid, id)
}

#[derive(thiserror::Error, Debug)]
enum AppError {
	#[error("redis error")]
	Redis(#[from] redis::RedisError),

	#[error("json error")]
	Json(#[from] serde_json::Error),


	#[error("yaml error")]
	Yaml(#[from] serde_yaml::Error),

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
			AppError::Yaml(e) => (StatusCode::INTERNAL_SERVER_ERROR, format!("yaml error: {}", e)).into_response(),
			AppError::NotFound => StatusCode::NOT_FOUND.into_response(),
			AppError::Duplicate => StatusCode::CONFLICT.into_response(),
			AppError::Parameter(e) => (StatusCode::BAD_REQUEST, format!("parameter error: {}", e)).into_response(),
		}
	}
}
