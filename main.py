import os
import zlib
import json
import base64

from PIL import Image
from typing import NamedTuple
from collections import defaultdict
from enum import IntEnum

Point = tuple[int, int]
ColorRGB = tuple[int, int, int]


class Color(IntEnum):
    BLACK = 0
    WHITE = 1
    BLUE = 2
    YELLOW = 3
    CYAN = 4
    PINK = 5
    RED = 6
    ORANGE = 7
    NAVY = 8
    GRAY = 9

    @staticmethod
    def is_any_path_color(px: 'Color') -> bool:
        """ Returns `true` if `px` is found on any path tile. """
        return px == Color.GRAY or px == Color.WHITE or px == Color.YELLOW or px == Color.RED or px == Color.CYAN


class Direction(IntEnum):
    """
    Convention is Quad IV, so UP = -y, DOWN = +y, LEFT = -x, RIGHT = +x
    """
    UP = 0
    RIGHT = 1
    DOWN = 2
    LEFT = 3

class TileType(IntEnum):
    # Straight H/V are named for the directions that ARE included
    STRAIGHT_H = 0
    STRAIGHT_H_GHOST_SLOW = 1
    STRAIGHT_V = 2
    # Curve X_Y are named for X,Y which are directions IN the curve
    CURVE_UP_LEFT = 3
    CURVE_UP_RIGHT = 4
    CURVE_DOWN_LEFT = 5
    CURVE_DOWN_RIGHT = 6
    # T_X is named for the direction X which is NOT IN the T-intersection
    T_RIGHT = 7
    T_LEFT = 8
    T_UP = 9
    T_DOWN = 10
    T_DOWN_GHOST_RESTRICT = 11
    FOUR_WAY = 12
    # Edge_X is named for the edge of the board it is on - left or right edge
    EDGE_LEFT = 13
    EDGE_RIGHT = 14

    @staticmethod
    def to_player_type(tile: 'TileType') -> 'TileType':
        if tile == TileType.STRAIGHT_H_GHOST_SLOW:
            return TileType.STRAIGHT_H
        if tile == TileType.T_DOWN_GHOST_RESTRICT:
            return TileType.T_DOWN
        return tile
    
    @staticmethod
    def is_player_type(tile: 'TileType') -> bool:
        return TileType.to_player_type(tile) == tile
    
    @staticmethod
    def all_player_tiles():
        return filter(TileType.is_player_type, TileType)


def main():
    get_color, get_bg_color, get_text_color = load_textures()
    grid_to_tile_type: dict[Point, TileType] = load_grid(get_color)

    do_background('background/game', lambda x, y: c if (c := get_color(x, y)) == Color.BLUE or c == Color.PINK else None)
    do_background('background/victory', lambda x, y: Color.WHITE if (c := get_color(x, y)) == Color.BLUE or c == Color.PINK else None)
    do_background('background/title', lambda x, y: c if (c := get_bg_color(x, y)) != Color.BLACK else None)
    do_text('text/ready', get_text_color, 0)
    do_text('text/game_over', get_text_color, 5)
    do_dots_logic('_values', get_color, lambda v, _: v)
    do_dots_logic('_sequence', get_color, lambda _, v: len(v) - 100)
    do_dots_logic('_bitmask', get_color, lambda *_: 1 << 30)
    do_pacman_movement_logic(grid_to_tile_type)
    do_ghost_movement_logic(grid_to_tile_type)
    do_ghost_eye_movement_logic(get_color, 0)
    do_ghost_eye_movement_logic(get_color, 1)
    do_ghost_eye_movement_logic(get_color, 2)
    do_ghost_eye_movement_logic(get_color, 3)


def load_grid(get_color) -> dict[Point, TileType]:
    # Map Logic
    # Parse out the fully connected map consisting of all WHITE, GRAY, RED, YELLOW, CYAN pixels
    grid: set[Point] = set()  # All grid positions
    grid_ghost_restrict: set[Point] = set()  # Positions that restrict ghost's upward movement (YELLOW)
    grid_ghost_slow: set[Point] = set()  # Positions that slow a ghost's movement (CYAN)
    for x in range(WIDTH):
        for y in range(HEIGHT):
            px = get_color(x, y)
            if Color.is_any_path_color(px):
                grid.add((x, y))
            if px == Color.YELLOW:
                grid_ghost_restrict.add((x, y))
            if px == Color.CYAN:
                grid_ghost_slow.add((x, y))
            if px == Color.RED:
                print('BIG DOT', (x, y))
    
    # Grid -> Tile Mapping
    # Map each grid point to a tile type
    grid_to_tile_type: dict[Point, TileType] = {}
    for pos in grid:
        x, y = pos
        connect_up = (x, y - 1) in grid
        connect_down = (x, y + 1) in grid
        connect_left = (x - 1, y) in grid
        connect_right = (x + 1, y) in grid

        if pos in grid_ghost_restrict:
            assert connect_up and connect_left and connect_right and not connect_down, 'grid_ghost_restrict must be T_DOWN'
            grid_to_tile_type[pos] = TileType.T_DOWN_GHOST_RESTRICT
            continue
        
        if pos in grid_ghost_slow:
            match (connect_up, connect_down, connect_left, connect_right):
                case (False, False, True, True):
                    grid_to_tile_type[pos] = TileType.STRAIGHT_H_GHOST_SLOW
                case (False, False, False, True):
                    grid_to_tile_type[pos] = TileType.EDGE_LEFT
                    print('EDGE_LEFT', pos)
                case (False, False, True, False):
                    grid_to_tile_type[pos] = TileType.EDGE_RIGHT
                    print('EDGE_RIGHT', pos)
                case _:
                    assert False, 'Invalid connections (grid_gost_slow) up=%s, down=%s, left=%s, right=%s at pos=%s' % (connect_up, connect_down, connect_left, connect_right, pos)
            continue
        
        match (connect_up, connect_down, connect_left, connect_right):
            case (False, False, True, True):
                grid_to_tile_type[pos] = TileType.STRAIGHT_H
            case (True, True, False, False):
                grid_to_tile_type[pos] = TileType.STRAIGHT_V
            case (True, False, True, False):
                grid_to_tile_type[pos] = TileType.CURVE_UP_LEFT
            case (True, False, False, True):
                grid_to_tile_type[pos] = TileType.CURVE_UP_RIGHT
            case (False, True, True, False):
                grid_to_tile_type[pos] = TileType.CURVE_DOWN_LEFT
            case (False, True, False, True):
                grid_to_tile_type[pos] = TileType.CURVE_DOWN_RIGHT
            case (True, True, True, False):
                grid_to_tile_type[pos] = TileType.T_RIGHT
            case (True, True, False, True):
                grid_to_tile_type[pos] = TileType.T_LEFT
            case (False, True, True, True):
                grid_to_tile_type[pos] = TileType.T_UP
            case (True, False, True, True):
                grid_to_tile_type[pos] = TileType.T_DOWN
            case (True, True, True, True):
                grid_to_tile_type[pos] = TileType.FOUR_WAY
            case _:
                assert False, 'Invalid connections up=%s, down=%s, left=%s, right=%s at pos=%s' % (connect_up, connect_down, connect_left, connect_right, pos)

    return grid_to_tile_type


def do_background(name: str, get_color):
    """
    Builds a background sprite.
    - `encode_all = False` : Only considers BLUE + PINK pixels part of the background
    - `encode_all = True`  : Considers all pixels not BLACK part of the background
    """
    # Background
    # Create the 'background' blueprint, based on BLUE + PINK pixels
    bp = decode_and_write(
        '0eNrtml9P2zAUxb+Lny8o107SphKv+xIIVWlrwFqbVI4Lq1C++3xtVhhjbPKfN6svyWnj341zenRUeGGb/UketRoMW70wtR2Hia1uX9ikHoZ+T9rQHyRbsZ3cqp3UV9vxsFFDb0bNZmBq2MkfbIUzfHIJLWb6wXx+DZ/vgMnBKKOkZ7qT83o4HTZS20Xhq4WAHcfJXjsORLTrXfHqugF2piPRXjeWtFNabv1HlkCrGD3u1xv52D8pu4S9bvLvT78f21kuN3Y3z3RzH2bj8MW+fD3a/w32uuzavrdTlxHfn9kh75WezPpt3835SCM9KW1OVrnM6D9x9Y12/9deuv21Qx977YZesRt7wfsV14M0z6P+7sha7tjK6JME9qCltIPf9/tJzvQQx5M5nsxH3/xjGPkk9dk8quGBpvoD5Va/sAg8/+VRiAibYGab1OE2qYpNktqkCbcJz50mbbBNeEmTtDZZRNgkd5osw21S0iStTbpwm2DuNMEq2CdY4iStTzCixGLuPMHwFoslUBIbJaLGVtkTJbzHViVREhsloshW2RMlvMlWJVESGyW8ymKXPVGCuyx2JVESG6WLMEruROFVuFFKoqQ1Cg8vs7jM/otscJnFZUmUxEYREUbJnih1uFFKoiQ2SniZxUX2RAkus7goiZLYKBFldpE9UcLL7KIkSmKjRJTZNneiiPAy25ZESfxn44gy2+ZOFBFeZtuSKImNElFmm+yJEl5mm5IoiY0SUWab7IkSXmabkiiJjRJRZuvsiRJeZuuSKDFGsbhnu3kEu0Xg9LqDWw4INaA9ElapnWbPoXVaY7XWafYclk5bWG3pNHsOWDmxs6I9JJUUQO5kJBB6EkmAnoUEQ08jCdDzkIDoiSQBeiYSFD2VJOAei8TlnksScM/l7gZf75C43HM5cbnnkgTcczlxueeSBNxzOXG555IEwnM5cYXnkgTCcwVxheeSBOJ1b4krPJckEJ4riCs8lyQQniuIK4hrn5oy8mCf/tt/0gKzDpjcd6BpeVd3XdPwphUc5/knqJDWIA==',
        'background'
    )
    rows = sorted(
        [
            e
            for e in bp['blueprint']['entities']
            if e['name'] == 'constant-combinator'
        ],
        key=lambda e: e['position']['y']
    )

    for y in range(HEIGHT):
        obj = rows[y // 5]['control_behavior']['sections']['sections'][0]
        if 'filters' not in obj:
            obj['filters'] = values = []
        else:
            values = obj['filters']
        
        for x in range(WIDTH):
            px = get_color(x, y)
            if px is not None:
                values.append({
                    'index': len(values) + 1,
                    'name': CONSTANTS[x],
                    'quality': QUALITY[y % 5],
                    'comparator': '=',
                    'count': px
                })
    
    encode_and_write(bp, name)


def do_text(name: str, get_color, y_offset: int):
    bp, values = load_blueprint_single_combinator()

    for x in range(TEXT_WIDTH):
        for y in range(TEXT_HEIGHT):
            px = get_color(x, y + y_offset)
            if px is not None:
                values.append({
                    'index': len(values) + 1,
                    'name': CONSTANTS[TEXT_X + x],
                    'quality': QUALITY[y],
                    'comparator': '=',
                    'count': px
                })
    
    encode_and_write(bp, name)


def do_dots_logic(name: str, get_color, formula):
    # Foreground
    # Includes all WHITE pixels representing the individual dots
    bp, values = load_blueprint_single_combinator()

    count = 0
    for x in range(WIDTH):
        value = 0
        
        for y in range(HEIGHT):
            px = get_color(x, y)
            if px == Color.WHITE or (px == Color.YELLOW and y != 34):
                y_index = ((y // 3) - 1)
                assert y_index < 30
                value |= 1 << y_index
                count += 1
      
        if value != 0:
            values.append({
                'index': len(values) + 1,
                'name': CONSTANTS[x],
                'quality': 'normal',
                'comparator': '=',
                'count': formula(value, values)
            })

    if name == '':
        print('DOTS', count)
    encode_and_write(bp, 'dots' + name)


def do_entity_tile_type_logic(
        name: str,
        grid_to_tile_type: dict[Point, Color],
        tile_type_set: set[TileType],
        tile_type_filter
    ):
    """
    Builds the logic used for tile type detection
    """
    
    acc = Accounter('TileMap[X, Y]')
    tile: TileType = Term('T')

    # Consistent ordering (by output value)
    for tile_type in tile_type_set:
        acc.by_output[tile == tile_type] = Term3([])

    # Then add each tile type by position
    for (x, y), tile_type in grid_to_tile_type.items():
        acc.if_then(
            (Term('X') == x) & (Term('Y') == y),
            tile == tile_type_filter(tile_type)
        )
    
    encode_and_write(acc.build(), name)


def do_pacman_movement_logic(grid_to_tile_type: dict[Point, Color]):
    """
    ===== PacMan Movement Logic =====
    
    PacMan movement has a few components that must be gotten right:
      1. Movement does not need to be held - pacman has a 'current direction' that will continue moving in
      2. When a direction is pressed that pacman cannot move in (due to a wall), it is queued in a buffer and will update
        at the next point in time pacman can move in that direction
     
    As a result of these, on any given tick we have three 'Direction' variables:
      D1 := The current input of the controller (may be -1)
      D2 := The current direction PacMan is moving in (may be -1, only at the start of the game)
      D3 := The last buffered movement command (may be -1, only at the start of the game)
    
    Both D2 and D3 get written to registers at the end of the movement, and `move` is used to choose the next position of PacMan.
    
    ```
    d1 | d2 | d3 | Action
    ---+----+----+--------
    -1 | -1 | ?? |     d2 <= -1, d3 <= -1, move <= -1
                 |
    D1 | -1 | ?? | if can_move(D1):
                 |     d2 <= D1, d3 <= -1, move <= D1
                 |
    -1 | D2 | -1 | if can_move(D2):
                 |     d2 <= D2, d3 <= -1, move <= D2
                 | else:
                 |     d2 <= D2, d3 <= -1, move <= -1
                 |
    D1 | D2 | ?? | if can_move(D1):
                 |     d2 <= D1, d3 <= -1, move <= D1
                 | elif can_move(D2):
                 |     d2 <= D2, d3 <= D1, move <= D2
                 | else:
                 |     d2 <= D2, d3 <= D1, move <= -1
                 |
    -1 | D2 | D3 | if can_move(D3):
                 |     d2 <= D3, d3 <= -1, move <= D3
                 | elif can_move(D2):
                 |     d2 <= D2, d3 <= D3, move <= D2
                 | else:
                 |     d2 <= D2, d3 <= D3, move <= -1
    ```
    """

    tile: TileType = Term('T')
    d1: Direction = Term('D1')
    d2: Direction = Term('D2')
    d3: Direction = Term('D3')

    # Compute the TileType[X, Y] map for the player
    do_entity_tile_type_logic('pacman/tile_type', grid_to_tile_type, TileType.all_player_tiles(), TileType.to_player_type)

    # Compute the can_move() functions for D1, D2, and D3, taking input the tile type and directions
    # N.B. These structures compute can_move(DN), from the inputs tile and `DN`
    encode_and_write(ai_can_move(tile, d1).build(), 'pacman/d1_can_move')
    encode_and_write(ai_can_move(tile, d2).build(), 'pacman/d2_can_move')
    encode_and_write(ai_can_move(tile, d3).build(), 'pacman/d3_can_move')

    d1_can_move = Term('M1')  # 1 if can_move(D1)
    d2_can_move = Term('M2')  # 1 if can_move(D2)
    d3_can_move = Term('M3')  # 1 if can_move(D3)

    # --- Calculate d2_next ---
    d2_next = Accounter('D2 Next')
    d2_next.if_then(
        (d1 == -1) & (d2 == -1),
        (d2, 'D2 <= -1')
    )
    d2_next.if_then(
        (d1 != -1) & (d1_can_move == 1),
        (d2, 'D2 <= D1')
    )
    d2_next.if_then(
        ((d1 == -1) & (d2 != -1) & (d3 == -1)) |
        ((d1 != -1) & (d2 != -1) & (d1_can_move == 0)) |
        ((d1 == -1) & (d2 != -1) & (d3 != -1) & (d3_can_move == 0)),
        (d2, 'D2 <= D2')
    )
    d2_next.if_then(
        (d1 == -1) & (d2 != -1) & (d3 != -1) & (d3_can_move == 1),
        (d2, 'D2 <= D3')
    )
    
    # --- Calculate d3_next ---
    d3_next = Accounter('D3 Next')
    d3_next.if_then(
        (d2 == -1) |
        ((d1 == -1) & (d2 != -1) & (d3 == -1)) |
        ((d1 != -1) & (d2 != -1) & (d1_can_move == 1)) |
        ((d1 == -1) & (d2 != -1) & (d3 != -1) & (d3_can_move == 1)),
        (d3, 'D3 <= -1')
    )
    d3_next.if_then(
        (d1 != -1) & (d2 != -1) & (d1_can_move == 0),
        (d3, 'D3 <= D1')
    )
    d3_next.if_then(
        (d1 == -1) & (d2 != -1) & (d3 != -1) & (d3_can_move == 0),
        (d3, 'D3 <= D3')
    )
    
    # --- Calculate move ---
    d = Term('D')
    d_move = Accounter('D Move')
    d_move.if_then(
        ((d1 == -1) & (d2 == -1)) |
        ((d1 == -1) & (d2 != -1) & (d3 == -1) & (d2_can_move == 0)) |
        ((d1 != -1) & (d2 != -1) & (d1_can_move == 0) & (d2_can_move == 0)) |
        ((d1 == -1) & (d2 != -1) & (d3 != -1) & (d2_can_move == 0) & (d3_can_move == 0)),
        (d, 'D_MOVE <= -1')
    )
    d_move.if_then(
        ((d1 != -1) & (d1_can_move == 1)) |
        ((d1 != -1) & (d2 != -1) & (d1_can_move == 1)),
        (d, 'D_MOVE <= D1')
    )
    d_move.if_then(
        ((d1 == -1) & (d2 != -1) & (d3 == -1) & (d2_can_move == 1)) |
        ((d1 != -1) & (d2 != -1) & (d1_can_move == 0) & (d2_can_move == 1)) |
        ((d1 == -1) & (d2 != -1) & (d3 != -1) & (d3_can_move == 0) & (d2_can_move == 1)),
        (d, 'D_MOVE <= D2')
    )
    d_move.if_then(
        (d1 == -1) & (d2 != -1) & (d3 != -1) & (d3_can_move == 1),
        (d, 'D_MOVE <= D3')
    )

    encode_and_write(d2_next.build(), 'pacman/d2_next')
    encode_and_write(d3_next.build(), 'pacman/d3_next')
    encode_and_write(d_move.build(), 'pacman/d_move')
    
    # ----- PacMan Animation -----
    # PacMan animation is done at the frame level, but we need to report (1) if we are moving, which
    # is done by storing D_MOVE, and (2) the direction we are facing, which we can compute from D_MOVE
    # and D2

    f = Term('F')
    facing = Accounter()
    for dir in Direction:
        facing.if_then(
            (d == dir) | ((d == -1) & (d2 == dir)),
            f == dir
        )
    
    encode_and_write(facing.build(), 'pacman/facing')


def ai_can_move(
        tile: 'TileType',
        dir: 'Direction'
    ) -> 'Accounter':
    can_move = Accounter()
    can_move.if_then(
        ((tile == TileType.STRAIGHT_H) & (dir == Direction.LEFT)) |
        ((tile == TileType.STRAIGHT_H) & (dir == Direction.RIGHT)) |
        ((tile == TileType.STRAIGHT_V) & (dir == Direction.UP)) |
        ((tile == TileType.STRAIGHT_V) & (dir == Direction.DOWN)) |
        
        ((tile == TileType.CURVE_UP_LEFT) & (dir == Direction.UP)) |
        ((tile == TileType.CURVE_UP_LEFT) & (dir == Direction.LEFT)) |
        ((tile == TileType.CURVE_UP_RIGHT) & (dir == Direction.UP)) |
        ((tile == TileType.CURVE_UP_RIGHT) & (dir == Direction.RIGHT)) |
        ((tile == TileType.CURVE_DOWN_LEFT) & (dir == Direction.DOWN)) |
        ((tile == TileType.CURVE_DOWN_LEFT) & (dir == Direction.LEFT)) |
        ((tile == TileType.CURVE_DOWN_RIGHT) & (dir == Direction.DOWN)) |
        ((tile == TileType.CURVE_DOWN_RIGHT) & (dir == Direction.RIGHT)) |

        ((tile == TileType.T_RIGHT) & (dir != Direction.RIGHT)) |
        ((tile == TileType.T_LEFT) & (dir != Direction.LEFT)) |
        ((tile == TileType.T_UP) & (dir != Direction.UP)) |
        ((tile == TileType.T_DOWN) & (dir != Direction.DOWN)) |

        (tile == TileType.FOUR_WAY) |
        
        ((tile == TileType.EDGE_LEFT) & (dir == Direction.LEFT)) |
        ((tile == TileType.EDGE_LEFT) & (dir == Direction.RIGHT)) |
        
        ((tile == TileType.EDGE_RIGHT) & (dir == Direction.LEFT)) |
        ((tile == TileType.EDGE_RIGHT) & (dir == Direction.RIGHT)),
        'true'
    )
    return can_move


def do_ghost_movement_logic(grid_to_tile_type: dict[Point, Color]):
    """
    incoming_dir := The direction of the ghost prior to the current tile

    === Choosing Direction ===

    The official method of choosing direction, is to choose whichever tile is closer to the target. We have a number of useful
    "proxy" fields which we can calculate, which are helpful when given a choice between two target tiles given a limited number
    of choices.

    - H  := 1 if Xt >= X else 0
    - V  := 1 if Yt <  Y else 0
    - S1 := 1 if Yt - Y > Xt - X else 0  # above y=x
    - S2 := 1 if Yt - Y > X - Xt else 0  # above y=-x

    This forms the following map, centered on (X, Y), of the octants where (Xt, Yt) is placed:
    (Note this is in Quadrant IV semantics, so origin is top left, +x/+y is bottom right)
    
      \C|B/       where
     D \|/ A          H  = 1 <=> { A, B,          G, H }
    ----+----         V  = 1 <=> { A, B, C, D          }
     E /|\ H          S1 = 1 <=> {    B, C, D, E       }
      /F|G\           S2 = 1 <=> { A, B, C,          H }

      
    === Frightened Movement ===

    When frightened, ghosts continue moving along their path, and pick a random direction at each intersection. The randomness
    is provided via two signals, R3 = {0, 1, 2} and R4 = {0, 1, 2, 3}, which are pseudorandom and uniformly distributed.

    Note that ghost speed when frightened is 50% of their normal speed, which means we actually only choose a new position
    and direction every _other_ tick. We do this with a simple latch which flips every tick

    """

    tile: TileType = Term('T')

    # Ghost Tile Type
    do_entity_tile_type_logic('ghost/tile_type', grid_to_tile_type, TileType, lambda x: x)

    # ----- Movement Logic -----
    # Ghost movement will always be one of straight, left, or right. We compute +1 | 0 | -1, add to D, then pass that
    # through logic to determine D' and X,Y
    incoming_dir: Direction = Term('D')
    flag_h: 0 | 1 = Term('H')
    flag_v: 0 | 1 = Term('V')
    flag_s1: 0 | 1 = Term('S1')
    flag_s2: 0 | 1 = Term('S2')

    acc = Accounter()
    acc.if_then(
    (
        (tile == TileType.STRAIGHT_H) |
        (tile == TileType.STRAIGHT_H_GHOST_SLOW) |
        (tile == TileType.STRAIGHT_V) |

        (tile == TileType.EDGE_LEFT) |
        (tile == TileType.EDGE_RIGHT) |

        ((tile == TileType.T_RIGHT) & (incoming_dir == Direction.DOWN) & (flag_s1 == 0)) |
        ((tile == TileType.T_RIGHT) & (incoming_dir == Direction.UP) & (flag_s2 == 1)) |

        ((tile == TileType.T_LEFT) & (incoming_dir == Direction.DOWN) & (flag_s2 == 0)) |
        ((tile == TileType.T_LEFT) & (incoming_dir == Direction.UP) & (flag_s1 == 1)) |

        ((tile == TileType.T_UP) & (incoming_dir == Direction.LEFT) & (flag_s1 == 1)) |
        ((tile == TileType.T_UP) & (incoming_dir == Direction.RIGHT) & (flag_s2 == 1)) |

        ((tile == TileType.T_DOWN) & (incoming_dir == Direction.LEFT) & (flag_s2 == 0)) |
        ((tile == TileType.T_DOWN) & (incoming_dir == Direction.RIGHT) & (flag_s1 == 0)) |

        ((tile == TileType.T_DOWN_GHOST_RESTRICT) & (incoming_dir == Direction.LEFT)) |
        ((tile == TileType.T_DOWN_GHOST_RESTRICT) & (incoming_dir == Direction.RIGHT)) |

        # Four-Way handling has several considerations:
        # - Straight movement is per-direction, we consider just the \/ shape (from S1 and S2) that matches the outgoing direction
        # - Left + Right turns match the same \/ shapes in the left and right exits
        # However, due to lack of moving backwards, we also need to handle the /\ case, for the reverse direction, by splitting
        # it among left/right turns. We have to do this in separate cases, because we cannot overlap existing cases.
        ((tile == TileType.FOUR_WAY) & (incoming_dir == Direction.UP) & (flag_s1 == 1) & (flag_s2 == 1)) |
        ((tile == TileType.FOUR_WAY) & (incoming_dir == Direction.RIGHT) & (flag_s1 == 0) & (flag_s2 == 1)) |
        ((tile == TileType.FOUR_WAY) & (incoming_dir == Direction.DOWN) & (flag_s1 == 0) & (flag_s2 == 0)) |
        ((tile == TileType.FOUR_WAY) & (incoming_dir == Direction.LEFT) & (flag_s1 == 1) & (flag_s2 == 0))

    ), 'straight')
    
    acc.if_then(
    (
        ((tile == TileType.CURVE_UP_LEFT) & (incoming_dir == Direction.RIGHT)) |
        ((tile == TileType.CURVE_UP_RIGHT) & (incoming_dir == Direction.DOWN)) |
        ((tile == TileType.CURVE_DOWN_LEFT) & (incoming_dir == Direction.UP)) |
        ((tile == TileType.CURVE_DOWN_RIGHT) & (incoming_dir == Direction.LEFT)) |

        ((tile == TileType.T_RIGHT) & (incoming_dir == Direction.UP) & (flag_s2 == 0)) |
        ((tile == TileType.T_RIGHT) & (incoming_dir == Direction.RIGHT) & (flag_v == 1)) |

        ((tile == TileType.T_LEFT) & (incoming_dir == Direction.DOWN) & (flag_s2 == 1)) |
        ((tile == TileType.T_LEFT) & (incoming_dir == Direction.LEFT) & (flag_v == 0)) | 

        ((tile == TileType.T_UP) & (incoming_dir == Direction.LEFT) & (flag_s1 == 0)) |
        ((tile == TileType.T_UP) & (incoming_dir == Direction.UP) & (flag_h == 0)) |

        ((tile == TileType.T_DOWN) & (incoming_dir == Direction.RIGHT) & (flag_s1 == 1)) |
        ((tile == TileType.T_DOWN) & (incoming_dir == Direction.DOWN) & (flag_h == 1)) |

        ((tile == TileType.T_DOWN_GHOST_RESTRICT) & (incoming_dir == Direction.DOWN) & (flag_h == 1)) |

        ((tile == TileType.FOUR_WAY) & (incoming_dir == Direction.RIGHT) & (flag_s1 == 1) & (flag_s2 == 1)) |
        ((tile == TileType.FOUR_WAY) & (incoming_dir == Direction.DOWN) & (flag_s1 == 0) & (flag_s2 == 1)) |
        ((tile == TileType.FOUR_WAY) & (incoming_dir == Direction.LEFT) & (flag_s1 == 0) & (flag_s2 == 0)) |
        ((tile == TileType.FOUR_WAY) & (incoming_dir == Direction.UP) & (flag_s1 == 1) & (flag_s2 == 0)) |

        # Extra 4-way cases for splitting the reverse direction
        ((tile == TileType.FOUR_WAY) & (incoming_dir == Direction.UP) & (flag_s1 == 0) & (flag_s2 == 0) & (flag_h == 1)) |
        ((tile == TileType.FOUR_WAY) & (incoming_dir == Direction.RIGHT) & (flag_s1 == 1) & (flag_s2 == 0) & (flag_v == 1)) |
        ((tile == TileType.FOUR_WAY) & (incoming_dir == Direction.DOWN) & (flag_s1 == 1) & (flag_s2 == 1) & (flag_h == 0)) |
        ((tile == TileType.FOUR_WAY) & (incoming_dir == Direction.LEFT) & (flag_s1 == 0) & (flag_s2 == 1) & (flag_v == 0))

    ), 'left turn')

    acc.if_then(
    (
        ((tile == TileType.CURVE_UP_LEFT) & (incoming_dir == Direction.DOWN)) |
        ((tile == TileType.CURVE_UP_RIGHT) & (incoming_dir == Direction.LEFT)) |
        ((tile == TileType.CURVE_DOWN_LEFT) & (incoming_dir == Direction.RIGHT)) |
        ((tile == TileType.CURVE_DOWN_RIGHT) & (incoming_dir == Direction.UP)) |

        ((tile == TileType.T_RIGHT) & (incoming_dir == Direction.DOWN) & (flag_s1 == 1)) |
        ((tile == TileType.T_RIGHT) & (incoming_dir == Direction.RIGHT) & (flag_v == 0)) |

        ((tile == TileType.T_LEFT) & (incoming_dir == Direction.UP) & (flag_s1 == 0)) |
        ((tile == TileType.T_LEFT) & (incoming_dir == Direction.LEFT) & (flag_v == 1)) |

        ((tile == TileType.T_UP) & (incoming_dir == Direction.RIGHT) & (flag_s2 == 0)) |
        ((tile == TileType.T_UP) & (incoming_dir == Direction.UP) & (flag_h == 1)) |

        ((tile == TileType.T_DOWN) & (incoming_dir == Direction.LEFT) & (flag_s2 == 1)) |
        ((tile == TileType.T_DOWN) & (incoming_dir == Direction.DOWN) & (flag_h == 0)) |

        ((tile == TileType.T_DOWN_GHOST_RESTRICT) & (incoming_dir == Direction.DOWN) & (flag_h == 0)) |

        ((tile == TileType.FOUR_WAY) & (incoming_dir == Direction.LEFT) & (flag_s1 == 1) & (flag_s2 == 1)) |
        ((tile == TileType.FOUR_WAY) & (incoming_dir == Direction.UP) & (flag_s1 == 0) & (flag_s2 == 1)) |
        ((tile == TileType.FOUR_WAY) & (incoming_dir == Direction.RIGHT) & (flag_s1 == 0) & (flag_s2 == 0)) |
        ((tile == TileType.FOUR_WAY) & (incoming_dir == Direction.DOWN) & (flag_s1 == 1) & (flag_s2 == 0)) |

        # Extra 4-way cases for splitting the reverse direction
        ((tile == TileType.FOUR_WAY) & (incoming_dir == Direction.UP) & (flag_s1 == 0) & (flag_s2 == 0) & (flag_h == 0)) |
        ((tile == TileType.FOUR_WAY) & (incoming_dir == Direction.RIGHT) & (flag_s1 == 1) & (flag_s2 == 0) & (flag_v == 0)) |
        ((tile == TileType.FOUR_WAY) & (incoming_dir == Direction.DOWN) & (flag_s1 == 1) & (flag_s2 == 1) & (flag_h == 1)) |
        ((tile == TileType.FOUR_WAY) & (incoming_dir == Direction.LEFT) & (flag_s1 == 0) & (flag_s2 == 1) & (flag_v == 1))

    ), 'right turn')

    encode_and_write(acc.build(), 'ghost/turn')

    # Frightened (Random) movement
    r3: 0 | 1 | 2 = Term('R3')
    r4: 0 | 1 | 2 | 3 = Term('R4')
    outgoing_dir: Direction = Term('D')

    acc = Accounter()
    acc.if_then((

        ((tile == TileType.STRAIGHT_V) & (incoming_dir == Direction.UP)) |

        ((tile == TileType.CURVE_UP_LEFT) & (incoming_dir == Direction.RIGHT)) |
        ((tile == TileType.CURVE_UP_RIGHT) & (incoming_dir == Direction.LEFT)) |

        ((tile == TileType.T_RIGHT) & (r3 == 0)) |
        ((tile == TileType.T_LEFT) & (r3 == 0)) |
        ((tile == TileType.T_DOWN) & (r3 == 0)) |
        ((tile == TileType.T_DOWN_GHOST_RESTRICT) & (r3 == 0)) |

        ((tile == TileType.FOUR_WAY) & (r4 == 0))

    ), outgoing_dir == Direction.UP)

    acc.if_then((

        ((tile == TileType.STRAIGHT_H) & (incoming_dir == Direction.RIGHT)) |
        ((tile == TileType.STRAIGHT_H_GHOST_SLOW) & (incoming_dir == Direction.RIGHT)) |
        ((tile == TileType.EDGE_LEFT) & (incoming_dir == Direction.RIGHT)) |
        ((tile == TileType.EDGE_RIGHT) & (incoming_dir == Direction.RIGHT)) |

        ((tile == TileType.CURVE_UP_RIGHT) & (incoming_dir == Direction.DOWN)) |
        ((tile == TileType.CURVE_DOWN_RIGHT) & (incoming_dir == Direction.UP)) |

        ((tile == TileType.T_LEFT) & (r3 == 1)) |
        ((tile == TileType.T_UP) & (r3 == 0)) |
        ((tile == TileType.T_DOWN) & (r3 == 1)) |
        ((tile == TileType.T_DOWN_GHOST_RESTRICT) & (r3 == 1)) |

        ((tile == TileType.FOUR_WAY) & (r4 == 1))

    ), outgoing_dir == Direction.RIGHT)

    acc.if_then((

        ((tile == TileType.STRAIGHT_V) & (incoming_dir == Direction.DOWN)) |

        ((tile == TileType.CURVE_DOWN_LEFT) & (incoming_dir == Direction.RIGHT)) |
        ((tile == TileType.CURVE_DOWN_RIGHT) & (incoming_dir == Direction.LEFT)) |

        ((tile == TileType.T_RIGHT) & (r3 == 1)) |
        ((tile == TileType.T_LEFT) & (r3 == 2)) |
        ((tile == TileType.T_UP) & (r3 == 1)) |
        
        ((tile == TileType.FOUR_WAY) & (r4 == 2))

    ), outgoing_dir == Direction.DOWN)

    acc.if_then((

        ((tile == TileType.STRAIGHT_H) & (incoming_dir == Direction.LEFT)) |
        ((tile == TileType.STRAIGHT_H_GHOST_SLOW) & (incoming_dir == Direction.LEFT)) |
        ((tile == TileType.EDGE_LEFT) & (incoming_dir == Direction.LEFT)) |
        ((tile == TileType.EDGE_RIGHT) & (incoming_dir == Direction.LEFT)) |

        ((tile == TileType.CURVE_UP_LEFT) & (incoming_dir == Direction.DOWN)) |
        ((tile == TileType.CURVE_DOWN_LEFT) & (incoming_dir == Direction.UP)) |

        ((tile == TileType.T_RIGHT) & (r3 == 2)) |
        ((tile == TileType.T_UP) & (r3 == 2)) |
        ((tile == TileType.T_DOWN) & (r3 == 2)) |
        ((tile == TileType.T_DOWN_GHOST_RESTRICT) & (r3 == 2)) |

        ((tile == TileType.FOUR_WAY) & (r4 == 3))

    ), outgoing_dir == Direction.LEFT)

    encode_and_write(acc.build(), 'ghost/random')


def do_ghost_eye_movement_logic(get_color: dict[Point, Color], ghost: int):
    """
    When a ghost gets 'eaten', the same sprite is re-used to do the eye movement logic, as the ghost
    finds it's way back to the home area. It does this with a procedurally generated path-finding setup.

    Ghost Eye movement is 2x faster than ghost movement; as a result, we have to compute two positions
    for the ghost each tick, and supply them one frame after the other.

    As the movement is entirely procedural, it relies on a map from (X, Y) -> (dX, dX2, dY, dY2), where
    the ghost position over time will be:
    T=0 : (X, Y)
    T=1 : (X + dX, Y + dY)
    T=2 : (X + dX2, Y + dY2)

    The lookup table for path movement consists of:
    - 12x movement steps of A, B (where A != reverse(B))
    - 1x movement steps of A, <none>, only used for the endpoint

    ```
     M  | dX, dY | dX2, dY2
     0  |  0,  1 |   0,  1
     1  |  0,  1 |  -1,  0
     2  |  0,  1 |   1,  0
     3  |  0, -1 |   0, -1
     4  |  0, -1 |  -1,  0
     5  |  0, -1 |   1,  0
     6  |  1,  0 |   1,  0
     7  |  1,  0 |   0, -1
     8  |  1,  0 |   0,  1
     9  | -1,  0 |  -1,  0
     10 | -1,  0 |   0, -1
     11 | -1,  0 |   0,  1
     12 |  ?,  ? |   0,  0

    Note that M=12 is unique, in the sense that it has a unique value per-ghost. As the path always
    has a consistent end point, and single end direction, we let M=12 be "whatever the movement needs
    to be for this ghosts' travel".

    Ghost 0 and 1 are (0, 1), Ghost 2 is (-1, 0), and Ghost 3 is (1, 0)
    ```
    """

    # In order to compute the eye movement lookup table, we need to BFS outwards from the 'return' point.
    origin = (41, 34)
    paths: dict[Point, Point] = dict()  # Mapping of (x, y) -> next (x, y)
    queue: list[Point] = [origin]
    visited: set[Point] = {origin}  # Visited positions

    # BFS
    while queue:
        pos = x, y = queue.pop(0)
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            next = x + dx, y + dy
            if next not in visited:
                px = get_color(*next)
                if Color.is_any_path_color(px):
                    paths[next] = pos
                    queue.append(next)
                    visited.add(next)
    
    # Also include paths from the origin, down into the ghost area (which are not noted in the texture)
    end = {
        0: (41, 41),
        1: (41, 44),
        2: (36, 44),
        3: (46, 44),
    }[ghost]

    for dy in range(end[1] - 34):
        paths[41, 34 + dy] = (41, 35 + dy)
    
    if end[0] != 41:
        sign = -1 if end[0] < 41 else +1 
        for dx in range(abs(end[0] - 41)):
            paths[41 + sign * dx, 44] = (41 + sign * (dx + 1), 44)
    
    # Include the endpoint, pointing to itself
    paths[end] = end
    
    # Now build the lookup table for every position we have saved paths for
    path_lookup: dict[Point, int] = dict()
    for pos in set(paths.keys()):  # Use this over visited as it includes the additional paths added above
        # Skip the endpoint, as it will be a no-op path
        if pos == end:
            continue

        x0, y0 = pos
        x1, y1 = paths[pos]
        x2, y2 = paths[x1, y1]
        match (x1 - x0, y1 - y0, x2 - x1, y2 - y1):
            case (0, 1, 0, 1):
                path_lookup[pos] = 0
            case (0, 1, -1, 0):
                path_lookup[pos] = 1
            case (0, 1, 1, 0):
                path_lookup[pos] = 2
            case (0, -1, 0, -1):
                path_lookup[pos] = 3
            case (0, -1, -1, 0):
                path_lookup[pos] = 4
            case (0, -1, 1, 0):
                path_lookup[pos] = 5
            case (1, 0, 1, 0):
                path_lookup[pos] = 6
            case (1, 0, 0, -1):
                path_lookup[pos] = 7
            case (1, 0, 0, 1):
                path_lookup[pos] = 8
            case (-1, 0, -1, 0):
                path_lookup[pos] = 9
            case (-1, 0, 0, -1):
                path_lookup[pos] = 10
            case (-1, 0, 0, 1):
                path_lookup[pos] = 11
            case (0, 1, 0, 0) | (-1, 0, 0, 0) | (1, 0, 0, 0):
                path_lookup[pos] = 12
            case _:
                assert False, 'Invalid path from %s -> %s -> %s' % (pos, (x1, y1), (x2, y2))
    
    # Build the lookup table
    acc = Accounter('PathLookup[X, Y]')
    path = Term('M')

    for m in range(13):
        acc.by_output[path == m] = Term3([])

    for (x, y), m in path_lookup.items():
        acc.if_then(
            (Term('X') == x) & (Term('Y') == y),
            path == m
        )
    
    encode_and_write(acc.build(), 'ghost/path_lookup_%d' % ghost)


def load_textures():
    """
    Loads all textures and builds a series of `get_color(x: int, y: int) -> Color` functions from them

    Returns a tuple of `get_color()` consisting of accessors for each of:
    - `texture.png`
    - `background.png`
    - `text.png`
    """
    os.makedirs('data', exist_ok=True)

    texture: Image = Image.open('assets/texture.png').convert('RGBA')
    background: Image = Image.open('assets/background.png').convert('RGBA')
    text: Image = Image.open('assets/text.png').convert('RGBA')

    # Color Mapping
    # Map of colors to their index, so we can easily refer to colors by constant, not RGB
    color_to_index: dict[ColorRGB, Color] = {}
    for x in range(10):  # Number of recorded colors (top left)
        color_to_index[texture.getpixel((x, 0))] = Color(len(color_to_index))
    
    def check(_texture: Image, _w: int = WIDTH, _h: int = HEIGHT):
        assert _texture.size == (_w, _h), 'Expected size=(%d, %d), got=%s' % (_w, _h, _texture.size)
        for _x in range(_w):
            for _y in range(_h):
                px = _texture.getpixel((_x, _y))
                assert px in color_to_index or px == (0, 0, 0, 0), 'Expected known color at %d, %d, got %s' % (_x, _y, _texture.getpixel((_x, _y)))

    check(texture, _h=HEIGHT + 5)
    check(background)
    check(text, _w=32, _h=10)

    def build(_texture: Image, _w: int = 0, _h: int = 0):
        def get_color(_x: int, _y: int) -> int | None:
            """ Return the grid color index at (x, y) """
            px = _texture.getpixel((_x + _w, _y + _h))
            return None if px == (0, 0, 0, 0) else color_to_index[px]
        return get_color

    texture_get_color = build(texture, _h=5)
    bg_get_color = build(background)
    text_get_color = build(text)

    return texture_get_color, bg_get_color, text_get_color


def load_blueprint_single_combinator():
    bp = decode_and_write(
        '0eNp9j00KgzAQhe8y61QwNbZ6lVIk6tAO6ESSKBXJ3ZvoQrrpbv7e995s0A4zTpbYQ70BdYYd1I8NHL1YD2nGekSoIW28Zn/pzNgSa28sBAHEPX6gzsNTALInT3gA9mZteB5btPFA/AMJmIyLWsPJMfIu8pYpAWuqCpmp6NSTxe44uYtE8dYMTYtvvVBERJ079u63jlnOkCGkoORxjEnO1wUsaN3OVqWsiqpSSqryKvMQvoDOYqA=',
        'rom'
    )
    bp['blueprint']['entities'][0]['control_behavior']['sections']['sections'][0]['filters'] = values = []
    return bp, values
    


def load(path: str):
    """ Load a BP JSON saved at /data/<path>.json """
    with open(f'data/{path}.json', 'r', encoding='utf-8') as f:
        return json.load(f)


def decode_and_write(text: str, path: str) -> dict:
    """ Decode a BP string and save the JSON to /data/<path>.json """
    blueprint = decode_blueprint_string(text)
    with open(f'data/{path}.json', 'w', encoding='utf-8') as f:
        json.dump(blueprint, f, ensure_ascii=True, indent=4)
    return blueprint

def encode_and_write(blueprint: dict, path: str):
    """ Encodes a BP JSON to a string an saves it to /data/<path>.txt """
    if '/' in path:
        os.makedirs('data/' + path[:path.rindex('/')], exist_ok=True)
    text = encode_blueprint_string(blueprint)
    with open(f'data/{path}.txt', 'w', encoding='utf-8') as f:
        f.write(text)


def decode_blueprint_string(blueprint: str) -> dict:
    version_char = blueprint[0]
    if version_char == '0':
        compressed = base64.b64decode(bytes(blueprint[1:], 'UTF-8'))
        text = zlib.decompress(compressed)
        return json.loads(text)
    else:
        raise ValueError('Unknown version byte %s' % version_char)


def encode_blueprint_string(blueprint: dict, version_char: str = '0') -> str:
    if version_char == '0':
        text = json.dumps(blueprint)
        compressed = zlib.compress(bytes(text, 'UTF-8'))
        return '0' + base64.b64encode(compressed).decode('UTF-8')
    else:
        raise ValueError('Unknown version byte %s' % version_char)


class Term(NamedTuple):
    value: str | int | IntEnum

    def __eq__(self, value): return Term1(self.value, '=', value)
    def __ne__(self, value): return Term1(self.value, '\u2260', value)
    
    def __repr__(self): return str(self.value)


class Term1(NamedTuple):
    lhs: Term
    op: str
    rhs: Term

    def __and__(self, value) -> 'Term2':
        if isinstance(value, Term1):
            return Term2([self, value])
        if isinstance(value, Term2):
            return Term2([self] + value.and_values)
        raise ValueError('%s and %s' % (repr(self), repr(value)))
    
    def __or__(self, value) -> 'Term3':
        if isinstance(value, Term1):
            return Term3([Term2([self]), Term2([value])])
        if isinstance(value, Term2):
            return Term3([Term2([self]), value])
        if isinstance(value, Term3):
            return Term3([Term2([self])] + value.or_values)
        raise ValueError('%s or %s' % (repr(self), repr(value)))

    def __repr__(self):
        return '%s %s %s' % (self.lhs, self.op, self.rhs)


class Term2(NamedTuple):
    and_values: list[Term1]

    def __and__(self, value) -> 'Term2':
        if isinstance(value, Term1):
            return Term2(self.and_values + [value])
        if isinstance(value, Term2):
            return Term2(self.and_values + value.and_values)
        raise ValueError('%s and %s' % (repr(self), repr(value)))
    
    def __or__(self, value) -> 'Term3':
        if isinstance(value, Term1):
            return Term3([self, Term2([value])])
        if isinstance(value, Term2):
            return Term3([self, value])
        if isinstance(value, Term3):
            return Term3([self] + value.or_values)
        raise ValueError('%s or %s' % (repr(self), repr(value)))
    
    def __repr__(self):
        return '(%s)' % ' and '.join(map(str, self.and_values))

class Term3(NamedTuple):
    or_values: list[Term2]

    def __and__(self, value): raise ValueError('%s and %s' % (repr(self), repr(value)))
    def __or__(self, value) -> 'Term3':
        if isinstance(value, Term1):
            return Term3(self.or_values + [Term2([value])])
        if isinstance(value, Term2):
            return Term3(self.or_values + [value])
        if isinstance(value, Term3):
            return Term3(self.or_values + value.or_values)
        raise ValueError('%s or %s' % (repr(self), repr(value)))

    def __repr__(self):
        return ' or '.join(map(str, self.or_values))

class Accounter:
    text: str
    by_output: dict[str | int | Term | Term1, Term3]

    def __init__(self, text: str = ''):
        self.by_output = defaultdict(lambda: Term3([]))
        self.text = text
    
    def if_then(self, term: Term3 | Term2 | Term1, output: str | int | Term1 | Term | tuple):
        self.by_output[output] |= term
    
    def __repr__(self): return 'Accounter[\n%s\n]' % '\n'.join('  if %s\n    then %s' % (v, k) for k, v in self.by_output.items())
    def __str__(self): return repr(self)

    def build(self) -> dict:
        """
        Builds a BP JSON for a sequence of combinators representing this LUT
        """
        bp = decode_and_write(
            '0eNqlk1FOwzAMhq+C/JwhbbRTV4kXJO4AQlOVNd6IaJOQpGPVlANwC87GSXDasY0xARuPcez//+zEa5hVDRorlYd8DbLUykH+sAYnF4pXMaZ4jZCDwFIKtINS1zOpuNcWAgOpBK4gH4YpA1Reeol9fXdoC9XUM7SUwH7QYWC0o1Ktoh/JZdllyqCFfDBKMnIR0mLZ32cMiNFbXRUzfORLSfVUtFEt6E50Si5G90/ENJfW+WLXmW9NJFpK6xuKbBH7jMFdbDAOxPM4nWE81IbbjjmHayrYVywU+hdtnzpniwJybxtksLCIBD7nlcMQ2MkY918xRidjdM5bjggVPjWw2JhzJeAMtoMRXX1jO6tfBs90Qd+Hgo0ixZpe/otRcmD0/vp24hj65zg+B/rLuvGm8Yer8Av5TYT86y/4p+qRRw1TEgZT8ZYWQaArrTT90sDtitemwguPK9/1Jz3WFN8tP4MlWtdlp+PRJJlM0jQdZsk4CeEDtbpwGA==',
            'lut'
        )

        bp['blueprint']['entities'] = entities = []
        for i, (out, term) in enumerate(self.by_output.items()):

            comment = self.text
            if type(out) == tuple:
                out, c = out
                comment += ', ' + c
            
            if comment != '':
                comment += ': '

            comment += 'Output %s' % str(out)
            
            if isinstance(out, Term1) and isinstance(out.rhs, IntEnum):
                comment += ' (%d)' % out.rhs.value

            entities.append({
                'entity_number': i + 1,
                'name': 'decider-combinator',
                'position': {
                    'x': i + 0.5,
                    'y': 0
                },
                'direction': 8,
                'control_behavior': {
                    'decider_conditions': {
                        'conditions': (conditions := []),
                        'outputs': (outputs := [])
                    }
                },
                'player_description': comment
            })

            if isinstance(out, Term):
                out = out == 'value'
            if isinstance(out, Term1):
                assert out.op == '='
                if out.rhs == 0:  # Output 0, so exclude it completely!
                    entities.pop(-1)
                    continue

                lhs = str(out.lhs)
                if out.rhs == 'value':
                    outputs.append({
                        'signal': {
                            'type': 'virtual',
                            'name': 'signal-%s' % lhs[0],
                            'quality': QUALITY[0 if len(lhs) == 1 else int(lhs[1]) - 1]
                        },
                        'networks': {
                            'red': False,
                            'green': True
                        }
                    })
                else:
                    outputs += [{
                        'signal': {
                            'type': 'virtual',
                            'name': 'signal-%s' % lhs[0],
                            'quality': QUALITY[0 if len(lhs) == 1 else int(lhs[1]) - 1]
                        },
                        'copy_count_from_input': False
                    }] * out.rhs
            else:
                outputs.append({})

            for or_value in term.or_values:
                for j, and_value in enumerate(or_value.and_values):
                    lhs = str(and_value.lhs)
                    conditions.append({
                        'first_signal': {
                            'type': 'virtual',
                            'name': 'signal-%s' % lhs[0],
                            'quality': QUALITY[0 if len(lhs) == 1 else int(lhs[1]) - 1]
                        },
                        'first_signal_networks': {
                            'red': True,
                            'green': False
                        },
                        'comparator': and_value.op,
                        'constant': and_value.rhs
                    })
                    if j != 0:
                        conditions[-1]['compare_type'] = 'and'
        return bp


# Factorio Constants
CONSTANTS = ['wooden-chest', 'iron-chest', 'steel-chest', 'storage-tank', 'transport-belt', 'fast-transport-belt', 'express-transport-belt', 'turbo-transport-belt', 'underground-belt', 'fast-underground-belt', 'express-underground-belt', 'turbo-underground-belt', 'splitter', 'fast-splitter', 'express-splitter', 'turbo-splitter', 'burner-inserter', 'inserter', 'long-handed-inserter', 'fast-inserter', 'bulk-inserter', 'stack-inserter', 'small-electric-pole', 'medium-electric-pole', 'big-electric-pole', 'substation', 'pipe', 'pipe-to-ground', 'pump', 'rail', 'rail-ramp', 'rail-support', 'train-stop', 'rail-signal', 'rail-chain-signal', 'locomotive', 'cargo-wagon', 'fluid-wagon', 'artillery-wagon', 'car', 'tank', 'spidertron', 'logistic-robot', 'construction-robot', 'active-provider-chest', 'passive-provider-chest', 'storage-chest', 'buffer-chest', 'requester-chest', 'roboport', 'small-lamp', 'arithmetic-combinator', 'decider-combinator', 'selector-combinator', 'constant-combinator', 'power-switch', 'programmable-speaker', 'display-panel', 'stone-brick', 'concrete', 'hazard-concrete', 'refined-concrete', 'refined-hazard-concrete', 'landfill', 'artificial-yumako-soil', 'overgrowth-yumako-soil', 'artificial-jellynut-soil', 'overgrowth-jellynut-soil', 'ice-platform', 'foundation', 'cliff-explosives', 'repair-pack', 'blueprint', 'deconstruction-planner', 'upgrade-planner', 'blueprint-book', 'boiler', 'steam-engine', 'solar-panel', 'accumulator', 'nuclear-reactor', 'heat-pipe', 'heat-exchanger', 'steam-turbine', 'fusion-reactor', 'fusion-generator', 'burner-mining-drill', 'electric-mining-drill', 'big-mining-drill', 'offshore-pump', 'pumpjack', 'stone-furnace', 'steel-furnace', 'electric-furnace', 'foundry', 'recycler', 'agricultural-tower', 'biochamber', 'captive-biter-spawner']
QUALITY = ['normal', 'uncommon', 'rare', 'epic', 'legendary']

# Dimensions (in px)
HEIGHT = 93
WIDTH = 84

# Text (in px)
TEXT_WIDTH = 32
TEXT_HEIGHT = 5
TEXT_X = 26
TEXT_Y = 50


if __name__ == '__main__':
    main()
