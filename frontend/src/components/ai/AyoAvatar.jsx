export default function AyoAvatar({ size = 36 }) {
  return <img className="ayo-avatar" src={`${import.meta.env.BASE_URL}ayo.png`} width={size} height={size} alt="" aria-hidden="true" />
}
