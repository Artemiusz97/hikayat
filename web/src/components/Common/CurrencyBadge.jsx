import {
  Coins,
  Crown,
  Disc,
  DollarSign,
  JapaneseYen,
  PoundSterling,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { getScenarioCurrency } from '../../utils/currency';

const ICON_MAP = {
  yen: JapaneseYen,
  dollar: DollarSign,
  pound: PoundSterling,
  caps: Disc,
  crown: Crown,
  coins: Coins,
};

const CurrencyBadge = ({
  amount = 0,
  scenario = 'fantasy',
  size = 'md',
  className = '',
}) => {
  const { t } = useTranslation();
  const cur = getScenarioCurrency(scenario);
  const CurrencyIcon = ICON_MAP[cur.icon] || Coins;
  const label = t(`currency.${cur.key}`, cur.name);
  const formattedNum = Number(amount || 0).toLocaleString();
  const isLg = size === 'lg';
  const isSm = size === 'sm';

  const glyphSize = cur.icon === 'cyber'
    ? (isLg ? 'text-xs' : isSm ? 'text-[9px]' : 'text-[10px]')
    : (isLg ? 'text-base' : isSm ? 'text-xs' : 'text-sm');

  return (
    <div
      title={label}
      aria-label={`${label}: ${formattedNum}`}
      className={`inline-flex items-center shrink-0 ${isLg ? 'gap-2' : isSm ? 'gap-1' : 'gap-1.5'} ${className}`}
    >
      <span
        className={`rounded-full bg-amber-500/12 border border-amber-500/35 text-amber-300 shadow-sm grid place-items-center shrink-0 ${
          isLg ? 'w-9 h-9' : isSm ? 'w-7 h-7' : 'w-8 h-8'
        }`}
      >
        {cur.icon === 'credit' || cur.icon === 'cyber' ? (
          <span className={`font-bold leading-none ${glyphSize}`}>{cur.symbol}</span>
        ) : (
          <CurrencyIcon size={isLg ? 16 : isSm ? 12 : 14} />
        )}
      </span>
      <div
        className={`rounded-xl bg-amber-500/12 border border-amber-500/35 text-amber-200 shadow-sm inline-flex items-center leading-none ${
          isLg ? 'h-9 px-3.5' : isSm ? 'h-7 px-2.5' : 'h-8 px-3'
        }`}
      >
        <div className={`inline-flex items-baseline leading-none ${isSm ? 'gap-1' : 'gap-1.5'}`}>
          <span className={`font-bold tabular-nums text-amber-200 ${isLg ? 'text-base' : isSm ? 'text-xs' : 'text-sm'}`}>
            {formattedNum}
          </span>
          <span
            className={`uppercase tracking-wider font-semibold text-amber-300/80 ${
              isLg ? 'text-[11px]' : isSm ? 'text-[9.5px]' : 'text-[10px]'
            }`}
          >
            {label}
          </span>
        </div>
      </div>
    </div>
  );
};

export default CurrencyBadge;
