export const GRID_SIZE = 16;

const DIRECTIONS = {
  up: { x: 0, y: -1 },
  down: { x: 0, y: 1 },
  left: { x: -1, y: 0 },
  right: { x: 1, y: 0 },
};

const OPPOSITES = {
  up: "down",
  down: "up",
  left: "right",
  right: "left",
};

function createInitialSnake() {
  return [
    { x: 8, y: 8 },
    { x: 7, y: 8 },
    { x: 6, y: 8 },
  ];
}

function serializePosition(position) {
  return `${position.x},${position.y}`;
}

function defaultRandom(max) {
  return Math.floor(Math.random() * max);
}

export function createFood(snake, gridSize, random = defaultRandom) {
  const occupied = new Set(snake.map(serializePosition));
  const openCells = [];

  for (let y = 0; y < gridSize; y += 1) {
    for (let x = 0; x < gridSize; x += 1) {
      if (!occupied.has(`${x},${y}`)) {
        openCells.push({ x, y });
      }
    }
  }

  if (openCells.length === 0) {
    return null;
  }

  return openCells[random(openCells.length)];
}

export function createInitialState(random = defaultRandom) {
  const snake = createInitialSnake();

  return {
    gridSize: GRID_SIZE,
    snake,
    direction: "right",
    queuedDirection: "right",
    food: createFood(snake, GRID_SIZE, random),
    score: 0,
    bestScore: 0,
    isGameOver: false,
    isPaused: false,
    hasStarted: false,
  };
}

export function queueDirection(state, nextDirection) {
  if (!DIRECTIONS[nextDirection] || state.isGameOver) {
    return state;
  }

  const activeDirection = state.hasStarted ? state.direction : state.queuedDirection;
  if (OPPOSITES[activeDirection] === nextDirection) {
    return state;
  }

  return { ...state, queuedDirection: nextDirection, hasStarted: true, isPaused: false };
}

export function togglePause(state) {
  if (state.isGameOver || !state.hasStarted) {
    return state;
  }

  return { ...state, isPaused: !state.isPaused };
}

export function stepGame(state, random = defaultRandom) {
  if (state.isGameOver || state.isPaused || !state.hasStarted) {
    return state;
  }

  const direction = state.queuedDirection;
  const movement = DIRECTIONS[direction];
  const head = state.snake[0];
  const nextHead = { x: head.x + movement.x, y: head.y + movement.y };
  const willEat = state.food && nextHead.x === state.food.x && nextHead.y === state.food.y;
  const nextSnake = willEat
    ? [nextHead, ...state.snake]
    : [nextHead, ...state.snake.slice(0, -1)];

  const hitsWall =
    nextHead.x < 0 ||
    nextHead.y < 0 ||
    nextHead.x >= state.gridSize ||
    nextHead.y >= state.gridSize;

  const hitsSelf = nextSnake
    .slice(1)
    .some((segment) => segment.x === nextHead.x && segment.y === nextHead.y);

  if (hitsWall || hitsSelf) {
    return {
      ...state,
      direction,
      snake: nextSnake,
      isGameOver: true,
      isPaused: false,
    };
  }

  const score = willEat ? state.score + 1 : state.score;
  const food = willEat ? createFood(nextSnake, state.gridSize, random) : state.food;

  return {
    ...state,
    direction,
    snake: nextSnake,
    food,
    score,
    bestScore: Math.max(state.bestScore, score),
  };
}

export function serializeCell(position) {
  return serializePosition(position);
}
