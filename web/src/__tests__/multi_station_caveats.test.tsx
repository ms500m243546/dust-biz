import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MultiStationCaveats } from '../components/MultiStationCaveats';

describe('MultiStationCaveats', () => {
  it('renders nothing when all caveats null', () => {
    const { container } = render(
      <MultiStationCaveats
        survivorCaveat={null}
        selectionCaveat={null}
        crossMineEval={null}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders survivor caveat when populated', () => {
    render(
      <MultiStationCaveats
        survivorCaveat="B-5 — only 2 receptors evaluated; station_count=5."
        selectionCaveat={null}
        crossMineEval={null}
      />,
    );
    expect(screen.getByTestId('caveat-survivor')).toBeInTheDocument();
    expect(screen.getByText(/2 receptors evaluated/)).toBeInTheDocument();
  });

  it('renders selection caveat when populated', () => {
    render(
      <MultiStationCaveats
        survivorCaveat={null}
        selectionCaveat="B-6 — per_receptor spans <2 distinct mines."
        crossMineEval={null}
      />,
    );
    expect(screen.getByTestId('caveat-selection')).toBeInTheDocument();
  });

  it('renders cross-mine eval block with mine list', () => {
    render(
      <MultiStationCaveats
        survivorCaveat={null}
        selectionCaveat={null}
        crossMineEval={{
          trained_on_mine: 'los-pelambres',
          evaluated_on_mines: ['los-bronces', 'chuquicamata'],
          cross_mine_receptors: ['lb-las-condes', 'chq-club-23-marzo'],
          warning: 'B-14 — cross-mine prediction',
        }}
      />,
    );
    expect(screen.getByTestId('caveat-cross-mine')).toBeInTheDocument();
    expect(screen.getByText(/los-pelambres/)).toBeInTheDocument();
    expect(screen.getByText(/los-bronces/)).toBeInTheDocument();
  });

  it('renders all three caveats together when all populated', () => {
    render(
      <MultiStationCaveats
        survivorCaveat="surv"
        selectionCaveat="sel"
        crossMineEval={{
          trained_on_mine: 't',
          evaluated_on_mines: ['e'],
          cross_mine_receptors: ['r'],
          warning: 'w',
        }}
      />,
    );
    expect(screen.getByTestId('caveat-survivor')).toBeInTheDocument();
    expect(screen.getByTestId('caveat-selection')).toBeInTheDocument();
    expect(screen.getByTestId('caveat-cross-mine')).toBeInTheDocument();
  });
});
